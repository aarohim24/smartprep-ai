"""
SmartPrep AI - Question Generation API
POST /api/v1/generate-questions
"""
import asyncio
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    QuestionGenerationRequest, QuestionGenerationResponse,
    InterviewQuestion, SessionTier,
)
from app.services.rag_service import rag_service
from app.services.llm_service import llm_service
from app.services.session_store import session_store
from app.utils.logger import setup_logger

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


@router.post("/generate-questions", response_model=QuestionGenerationResponse)
async def generate_questions(request: QuestionGenerationRequest):
    """
    Generate personalized interview questions using hybrid RAG pipeline:
    1. Retrieve relevant resume chunks for the JD (FAISS + BM25 + cross-encoder)
    2. Index job description into vector store (deduplicated)
    3. Generate mode-aware, tier-calibrated questions grounded in retrieved context
    """
    session = await session_store.get(request.session_id)
    if not session:
        raise HTTPException(404, "Session not found. Please upload your resume first.")

    if not rag_service.session_exists(request.session_id):
        raise HTTPException(404, "Resume index not found. Please re-upload your resume.")

    tier = request.tier or SessionTier.mixed
    mode = request.mode or None
    mode_value = mode.value if mode else "behavioral"

    # Derive question count from tier (tier takes priority over manual num_questions)
    num_questions = TIER_QUESTION_COUNTS.get(tier, request.num_questions)
    timer_seconds = TIER_TIMER_SECONDS.get(tier, 25 * 60)

    # Index JD and retrieve resume context in parallel — they are independent.
    # JD indexing dedup-guard in RAGService prevents double-indexing.
    async def _index_jd_safe():
        try:
            await rag_service.index_job_description(request.session_id, request.job_description)
        except Exception as e:
            logger.warning(f"JD indexing failed (non-critical): {e}")

    async def _retrieve_context_safe():
        try:
            return await rag_service.retrieve_for_questions(
                request.session_id, request.job_description
            )
        except Exception as e:
            logger.warning(f"RAG retrieval failed, falling back to raw resume: {e}")
            return ""

    _, context = await asyncio.gather(_index_jd_safe(), _retrieve_context_safe())

    if not context:
        context = session.get("resume_text", "")[:3000]

    # Generate questions via LLM (retries handled inside llm_service)
    try:
        result = await llm_service.generate_questions(
            resume_context=context,
            job_description=request.job_description,
            experience_level=request.experience_level.value,
            num_questions=num_questions,
            focus_areas=request.focus_areas,
            mode=mode_value,
            tier=tier.value,
        )
    except Exception as e:
        logger.error(f"Question generation failed: {e}", exc_info=True)
        raise HTTPException(500, "Failed to generate questions. Please try again.")

    # Parse and validate questions
    raw_questions = result.get("questions", [])
    questions = []
    for q in raw_questions:
        try:
            questions.append(InterviewQuestion(
                id=q.get("id", len(questions) + 1),
                question=q["question"],
                category=q.get("category", "General"),
                difficulty=q.get("difficulty", "Medium"),
                rationale=q.get("rationale", ""),
            ))
        except Exception as e:
            logger.warning(f"Skipping malformed question: {e}")

    if not questions:
        raise HTTPException(500, "No valid questions were generated. Please try again.")

    # Update session — store tier/mode for debrief
    await session_store.update(request.session_id, {
        "job_description": request.job_description,
        "questions": [q.model_dump() for q in questions],
        "tier": tier.value,
        "mode": mode_value,
    })

    logger.info(
        f"Generated {len(questions)} questions for session {request.session_id} "
        f"— mode={mode_value}, tier={tier.value}"
    )

    return QuestionGenerationResponse(
        session_id=request.session_id,
        questions=questions,
        job_role=result.get("job_role", "Software Engineer"),
        key_requirements=result.get("key_requirements", []),
        tier=tier,
        mode=mode,
        timer_seconds=timer_seconds,
    )
