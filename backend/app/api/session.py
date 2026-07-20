"""
SmartPrep AI - Session Debrief API
POST /api/v1/session-debrief
Returns a structured debrief report from all session results.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from app.models.schemas import (
    DebriefRequest, DebriefReport, CategoryBreakdown,
    SessionTier, RubricScores,
)
from app.services.llm_service import llm_service
from app.services.memory_service import memory_service
from app.services.session_store import session_store
from app.utils.logger import setup_logger
from app.utils.scoring import score_to_grade

logger = setup_logger(__name__)
router = APIRouter()


TIER_QUESTION_COUNTS = {
    SessionTier.easy: 5,
    SessionTier.mixed: 7,
    SessionTier.hard: 10,
}

TIER_TIMER_SECONDS = {
    SessionTier.easy: 15 * 60,
    SessionTier.mixed: 25 * 60,
    SessionTier.hard: 35 * 60,
}


def _suggest_next_tier(avg_score: float, current_tier: SessionTier) -> SessionTier:
    """Recommend the next session tier based on performance."""
    if avg_score >= 8.0 and current_tier != SessionTier.hard:
        tiers = [SessionTier.easy, SessionTier.mixed, SessionTier.hard]
        idx = tiers.index(current_tier)
        return tiers[min(idx + 1, 2)]
    elif avg_score < 5.0 and current_tier != SessionTier.easy:
        tiers = [SessionTier.easy, SessionTier.mixed, SessionTier.hard]
        idx = tiers.index(current_tier)
        return tiers[max(idx - 1, 0)]
    return current_tier


def _avg_rubric(results) -> Optional[RubricScores]:
    rubrics = [r.rubric_scores for r in results if r.rubric_scores]
    if not rubrics:
        return None
    n = len(rubrics)
    return RubricScores(
        correctness=round(sum(r.correctness for r in rubrics) / n, 1),
        completeness=round(sum(r.completeness for r in rubrics) / n, 1),
        communication=round(sum(r.communication for r in rubrics) / n, 1),
        problem_solving=round(sum(r.problem_solving for r in rubrics) / n, 1),
    )


@router.post("/session-debrief", response_model=DebriefReport)
async def session_debrief(request: DebriefRequest):
    """
    Generate a structured session debrief:
    - Category breakdown with rubric averages
    - Overall score + grade
    - Revisit list (questions scoring < 6)
    - Tier recommendation
    - LLM-generated strengths/improvement focus
    """
    session = await session_store.get(request.session_id)
    if not session:
        raise HTTPException(404, "Session not found. Please upload your resume first.")

    results = request.results
    if not results:
        raise HTTPException(400, "No results provided for debrief.")

    # ── Aggregations ───────────────────────────────────────────────────────────
    scores = [r.score for r in results]
    avg_score = round(sum(scores) / len(scores), 1)
    overall_grade = score_to_grade(avg_score)
    completion_rate = round(len(results) / TIER_QUESTION_COUNTS.get(request.tier, 7), 2)
    completion_rate = min(completion_rate, 1.0)

    # Category breakdown
    by_category: dict = {}
    for r in results:
        cat = r.category
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(r)

    category_breakdown = []
    for cat, cat_results in by_category.items():
        cat_scores = [r.score for r in cat_results]
        category_breakdown.append(CategoryBreakdown(
            category=cat,
            avg_score=round(sum(cat_scores) / len(cat_scores), 1),
            question_count=len(cat_results),
            rubric_avg=_avg_rubric(cat_results),
        ))
    category_breakdown.sort(key=lambda x: x.avg_score)

    # Revisit list: questions scoring < 6
    revisit_list = [
        f"Q{r.question_id}: {r.question[:80]}..."
        for r in results if r.score < 6.0
    ]

    # Tier recommendation
    suggested_next_tier = _suggest_next_tier(avg_score, request.tier)

    # LLM-generated debrief insights
    try:
        insights = await llm_service.generate_debrief_summary(
            mode=request.mode.value,
            tier=request.tier.value,
            results=[r.model_dump() for r in results],
            avg_score=avg_score,
        )
        strengths_summary = insights.get("strengths_summary", [])
        improvement_focus = insights.get("improvement_focus", [])
    except Exception as e:
        logger.warning(f"Debrief LLM insights failed (non-fatal): {e}")
        strengths_summary = [f"Average score: {avg_score}/10"]
        improvement_focus = [c.category for c in category_breakdown[:3]]

    logger.info(
        f"Debrief generated: session={request.session_id}, "
        f"avg={avg_score}, tier={request.tier}, mode={request.mode}, "
        f"revisit={len(revisit_list)} questions"
    )

    report = DebriefReport(
        session_id=request.session_id,
        overall_score=avg_score,
        grade=overall_grade,
        tier=request.tier,
        mode=request.mode,
        time_used_seconds=request.time_used_seconds,
        category_breakdown=category_breakdown,
        strengths_summary=strengths_summary,
        revisit_list=revisit_list,
        suggested_next_tier=suggested_next_tier,
        improvement_focus=improvement_focus,
        completion_rate=completion_rate,
    )

    # Persist to learner memory (non-blocking; uses candidate_id from session or session_id as fallback)
    candidate_id = request.session_id  # Use session_id as proxy until auth is added
    try:
        import asyncio
        asyncio.create_task(
            memory_service.persist_session(
                session_id=request.session_id,
                candidate_id=candidate_id,
                mode=request.mode.value,
                tier=request.tier.value,
                results=[r.model_dump() for r in results],
                time_used_seconds=request.time_used_seconds,
            )
        )
    except Exception as e:
        logger.warning(f"Memory persistence task creation failed (non-fatal): {e}")

    return report


@router.get("/learner/{candidate_id}/profile")
async def get_learner_profile(candidate_id: str):
    """
    Return a candidate's weakness graph, FSRS-scheduled review list,
    and cross-session performance trajectory.
    """
    try:
        profile = await memory_service.get_profile(candidate_id)
    except Exception as e:
        logger.error(f"Failed to get learner profile: {e}", exc_info=True)
        raise HTTPException(500, "Failed to retrieve learner profile.")

    return profile

