"""
SmartPrep AI - Learner Memory Service
Maintains per-candidate weakness graphs and FSRS-based spaced revision scheduling.
"""
import time
import math
from typing import Optional, List, Dict
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.db.models import Candidate, Session as DBSession, QuestionAttempt, SkillNode, FSRSCard
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# ── Simplified FSRS-4.5 constants ─────────────────────────────────────────────
FSRS_DECAY = -0.5
FSRS_FACTOR = 19 / 81
FSRS_DESIRED_RETENTION = 0.9
FSRS_W = [0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01, 1.49, 0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29, 2.61]


def _fsrs_stability_after_recall(stability: float, difficulty: float, retrievability: float) -> float:
    """Estimate new stability after a successful recall."""
    return stability * (
        math.e ** (FSRS_W[8] * (11 - difficulty) * stability ** (-FSRS_W[9]) * (math.e ** (FSRS_W[10] * (1 - retrievability)) - 1))
        + 1
    )


def _fsrs_retrievability(stability: float, days_elapsed: float) -> float:
    """Estimate memory retrievability given stability and elapsed days."""
    return (1 + FSRS_FACTOR * days_elapsed / stability) ** FSRS_DECAY


def _fsrs_interval(stability: float) -> float:
    """Calculate next review interval (days) to maintain desired retention."""
    return stability / FSRS_FACTOR * (FSRS_DESIRED_RETENTION ** (1 / FSRS_DECAY) - 1)


def _score_to_rating(score: float) -> int:
    """Map 0–10 score to FSRS rating (1=Again, 2=Hard, 3=Good, 4=Easy)."""
    if score >= 8.5:
        return 4   # Easy
    elif score >= 7.0:
        return 3   # Good
    elif score >= 5.0:
        return 2   # Hard
    else:
        return 1   # Again


class MemoryService:
    """
    Manages per-candidate skill weakness graphs and FSRS spaced revision.
    All methods use async SQLAlchemy sessions.
    """

    async def _ensure_candidate(self, db: AsyncSession, candidate_id: str) -> Candidate:
        result = await db.get(Candidate, candidate_id)
        if not result:
            result = Candidate(id=candidate_id)
            db.add(result)
            await db.flush()
        return result

    async def persist_session(
        self,
        session_id: str,
        candidate_id: str,
        mode: str,
        tier: str,
        results: List[dict],
        time_used_seconds: Optional[int] = None,
    ) -> None:
        """Persist a completed session and update the weakness graph."""
        async with AsyncSessionLocal() as db:
            try:
                await self._ensure_candidate(db, candidate_id)

                scores = [r.get("score", 0) for r in results]
                avg_score = sum(scores) / len(scores) if scores else 0

                def _avg_dim(dim: str):
                    vals = [
                        r.get("rubric_scores", {}).get(dim)
                        for r in results
                        if r.get("rubric_scores", {}).get(dim) is not None
                    ]
                    return sum(vals) / len(vals) if vals else None

                db_session = DBSession(
                    id=session_id,
                    candidate_id=candidate_id,
                    mode=mode,
                    tier=tier,
                    overall_score=avg_score,
                    avg_correctness=_avg_dim("correctness"),
                    avg_completeness=_avg_dim("completeness"),
                    avg_communication=_avg_dim("communication"),
                    avg_problem_solving=_avg_dim("problem_solving"),
                    completion_rate=min(len(results) / max(len(results), 1), 1.0),
                    time_used_seconds=time_used_seconds,
                )
                db.add(db_session)

                for r in results:
                    rubric = r.get("rubric_scores", {}) or {}
                    attempt = QuestionAttempt(
                        session_id=session_id,
                        candidate_id=candidate_id,
                        question_text=r.get("question", ""),
                        category=r.get("category", "General"),
                        difficulty=r.get("difficulty", "Medium"),
                        score=r.get("score", 0),
                        correctness=rubric.get("correctness"),
                        completeness=rubric.get("completeness"),
                        communication=rubric.get("communication"),
                        problem_solving=rubric.get("problem_solving"),
                        low_confidence=r.get("low_confidence_flag", False),
                    )
                    db.add(attempt)

                await self._update_weakness_graph(db, candidate_id, results)
                await self._update_fsrs_cards(db, candidate_id, results)
                await db.commit()
                logger.info(f"Persisted session {session_id} for candidate {candidate_id}")
            except Exception as e:
                await db.rollback()
                logger.error(f"Memory persist failed: {e}", exc_info=True)

    async def _update_weakness_graph(
        self, db: AsyncSession, candidate_id: str, results: List[dict]
    ) -> None:
        """Exponential moving average update for each skill × dimension node."""
        EMA_ALPHA = 0.3  # weight for new observation

        for r in results:
            rubric = r.get("rubric_scores", {}) or {}
            category = r.get("category", "General")

            for dimension in ("correctness", "completeness", "communication", "problem_solving"):
                dim_score = rubric.get(dimension)
                if dim_score is None:
                    dim_score = r.get("score", 5.0)

                # Look up existing node
                result_q = await db.execute(
                    select(SkillNode).where(
                        SkillNode.candidate_id == candidate_id,
                        SkillNode.skill == category,
                        SkillNode.dimension == dimension,
                    )
                )
                node = result_q.scalar_one_or_none()

                if node:
                    new_avg = (1 - EMA_ALPHA) * node.avg_score + EMA_ALPHA * dim_score
                    node.avg_score = round(new_avg, 2)
                    node.sample_count += 1
                    node.last_updated = time.time()
                else:
                    db.add(SkillNode(
                        candidate_id=candidate_id,
                        skill=category,
                        dimension=dimension,
                        avg_score=dim_score,
                        sample_count=1,
                    ))

    async def _update_fsrs_cards(
        self, db: AsyncSession, candidate_id: str, results: List[dict]
    ) -> None:
        """Add or update FSRS cards for weak answers (score < 7)."""
        for r in results:
            score = r.get("score", 5.0)
            if score >= 7.0:
                continue  # Only schedule weak answers

            question = r.get("question", "")
            category = r.get("category", "General")
            difficulty = r.get("difficulty", "Medium")
            rating = _score_to_rating(score)

            # Check for existing card
            result_q = await db.execute(
                select(FSRSCard).where(
                    FSRSCard.candidate_id == candidate_id,
                    FSRSCard.question_text == question,
                )
            )
            card = result_q.scalar_one_or_none()

            now = time.time()

            if card:
                # Update existing card
                days_elapsed = (now - (card.last_reviewed or card.created_at)) / 86400
                retrievability = _fsrs_retrievability(card.stability, days_elapsed)

                if rating >= 3:
                    new_stability = _fsrs_stability_after_recall(
                        card.stability, card.difficulty_fsrs, retrievability
                    )
                else:
                    # Lapse: reset stability
                    new_stability = max(FSRS_W[11], card.stability * FSRS_W[12])
                    card.lapses += 1

                card.stability = round(max(new_stability, 0.1), 2)
                card.reps += 1
                card.last_score = score
                card.last_reviewed = now
                interval_days = _fsrs_interval(card.stability)
                card.due_at = now + interval_days * 86400
            else:
                # New card
                initial_stability = FSRS_W[rating - 1] if rating <= 4 else 1.0
                interval_days = _fsrs_interval(initial_stability)
                db.add(FSRSCard(
                    candidate_id=candidate_id,
                    question_text=question,
                    category=category,
                    difficulty=difficulty,
                    stability=round(initial_stability, 2),
                    reps=1,
                    last_score=score,
                    last_reviewed=now,
                    due_at=now + interval_days * 86400,
                ))

    async def get_profile(self, candidate_id: str) -> dict:
        """Return the candidate's weakness graph, FSRS due list, and cross-session trajectory."""
        async with AsyncSessionLocal() as db:
            # Weakness graph
            result_q = await db.execute(
                select(SkillNode).where(SkillNode.candidate_id == candidate_id)
            )
            nodes = result_q.scalars().all()
            weakness_graph = [
                {
                    "skill": n.skill,
                    "dimension": n.dimension,
                    "avg_score": n.avg_score,
                    "sample_count": n.sample_count,
                }
                for n in nodes
            ]

            # FSRS due cards
            now = time.time()
            result_q = await db.execute(
                select(FSRSCard).where(
                    FSRSCard.candidate_id == candidate_id,
                    FSRSCard.due_at <= now,
                ).order_by(FSRSCard.due_at)
            )
            due_cards = result_q.scalars().all()
            fsrs_due = [
                {
                    "question": c.question_text,
                    "category": c.category,
                    "difficulty": c.difficulty,
                    "last_score": c.last_score,
                    "due_at": c.due_at,
                    "stability_days": c.stability,
                }
                for c in due_cards
            ]

            # Cross-session trajectory (last 10 sessions)
            result_q = await db.execute(
                select(DBSession).where(DBSession.candidate_id == candidate_id)
                .order_by(DBSession.created_at)
            )
            sessions = result_q.scalars().all()
            trajectory = [
                {
                    "session_id": s.id,
                    "mode": s.mode,
                    "tier": s.tier,
                    "overall_score": s.overall_score,
                    "correctness": s.avg_correctness,
                    "completeness": s.avg_completeness,
                    "communication": s.avg_communication,
                    "problem_solving": s.avg_problem_solving,
                    "created_at": s.created_at,
                }
                for s in sessions[-10:]
            ]

            return {
                "candidate_id": candidate_id,
                "weakness_graph": weakness_graph,
                "fsrs_due": fsrs_due,
                "trajectory": trajectory,
                "session_count": len(sessions),
            }


memory_service = MemoryService()
