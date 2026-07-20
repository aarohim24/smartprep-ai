"""
SmartPrep AI - Community Question Pool API
Allows candidates to submit their own prep questions, validated by the validator agent
before entering the shared pool.

Endpoints:
  POST /api/v1/questions/submit    — Submit a new question for validation
  POST /api/v1/questions/validate  — Validate without submitting (preview)
  GET  /api/v1/questions/pool      — Browse approved community questions
  GET  /api/v1/questions/pool/{id} — Get a specific community question
"""
import time
import uuid
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.validator_agent import validator_agent
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()

# ── In-memory question pool (replace with DB in production) ───────────────────
# Structure: { id: CommunityQuestion }
_question_pool: dict = {}


# ── Schemas ───────────────────────────────────────────────────────────────────

class QuestionSubmitRequest(BaseModel):
    question: str = Field(..., min_length=10, max_length=1000, description="The interview question text")
    category: str = Field(..., description="Technical | Behavioral | System Design | Coding | Situational")
    difficulty: str = Field(..., description="Easy | Medium | Hard")
    mode: str = Field(default="behavioral", description="coding | system_design | behavioral")
    submitter_note: Optional[str] = Field(None, max_length=300, description="Optional context from submitter")


class ValidationPreviewRequest(BaseModel):
    question: str = Field(..., min_length=10, max_length=1000)
    category: str
    difficulty: str


class CommunityQuestion(BaseModel):
    id: str
    question: str
    category: str
    difficulty: str
    mode: str
    submitter_note: Optional[str]
    quality_score: float
    approved: bool
    rejection_reasons: List[str]
    suggested_edit: Optional[str]
    suggested_difficulty: str
    is_duplicate: bool
    similar_question: Optional[str]
    submitted_at: float
    # Elo-style difficulty rating (updated as candidates attempt the question)
    elo_difficulty: float = 1000.0
    attempt_count: int = 0
    avg_score: Optional[float] = None


class QuestionSubmitResponse(BaseModel):
    question_id: str
    approved: bool
    rejection_reasons: List[str]
    quality_score: float
    suggested_edit: Optional[str]
    suggested_difficulty: str
    message: str


class PoolFilters(BaseModel):
    mode: Optional[str] = None
    category: Optional[str] = None
    difficulty: Optional[str] = None
    min_quality: float = 6.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_existing_questions() -> List[str]:
    """Return text of all approved questions for duplicate detection."""
    return [q.question for q in _question_pool.values() if q.approved]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/questions/submit", response_model=QuestionSubmitResponse)
async def submit_question(request: QuestionSubmitRequest):
    """
    Submit a new prep question. The validator agent runs 4 checks:
    answerability, difficulty accuracy, quality scoring, and duplicate detection.
    If all checks pass, the question enters the community pool immediately.
    """
    existing = _get_existing_questions()

    try:
        verdict = await validator_agent.validate(
            question=request.question,
            category=request.category,
            difficulty=request.difficulty,
            existing_questions=existing,
        )
    except Exception as e:
        logger.error(f"Validation failed: {e}", exc_info=True)
        raise HTTPException(500, "Validation service unavailable. Please try again.")

    question_id = str(uuid.uuid4())[:8]
    suggested_difficulty = verdict.get("suggested_difficulty", request.difficulty)

    community_q = CommunityQuestion(
        id=question_id,
        question=request.question,
        category=request.category,
        difficulty=suggested_difficulty,  # use validated difficulty
        mode=request.mode,
        submitter_note=request.submitter_note,
        quality_score=verdict["quality_score"],
        approved=verdict["approved"],
        rejection_reasons=verdict["rejection_reasons"],
        suggested_edit=verdict.get("suggested_edit"),
        suggested_difficulty=suggested_difficulty,
        is_duplicate=verdict.get("is_duplicate", False),
        similar_question=verdict.get("similar_question"),
        submitted_at=time.time(),
    )

    _question_pool[question_id] = community_q

    message = (
        "Question approved and added to the community pool!"
        if verdict["approved"]
        else "Question needs improvement before it can be added."
    )

    logger.info(
        f"Question submitted: id={question_id}, approved={verdict['approved']}, "
        f"quality={verdict['quality_score']:.1f}"
    )

    return QuestionSubmitResponse(
        question_id=question_id,
        approved=verdict["approved"],
        rejection_reasons=verdict["rejection_reasons"],
        quality_score=verdict["quality_score"],
        suggested_edit=verdict.get("suggested_edit"),
        suggested_difficulty=suggested_difficulty,
        message=message,
    )


@router.post("/questions/validate")
async def validate_question_preview(request: ValidationPreviewRequest):
    """
    Preview validation without submitting. Returns the full validator verdict
    so candidates can iterate on their question before final submission.
    """
    existing = _get_existing_questions()
    try:
        verdict = await validator_agent.validate(
            question=request.question,
            category=request.category,
            difficulty=request.difficulty,
            existing_questions=existing,
        )
    except Exception as e:
        logger.error(f"Validation preview failed: {e}", exc_info=True)
        raise HTTPException(500, "Validation service unavailable.")

    return {
        "preview": True,
        **verdict,
    }


@router.get("/questions/pool")
async def get_question_pool(
    mode: Optional[str] = Query(None, description="Filter by mode"),
    category: Optional[str] = Query(None, description="Filter by category"),
    difficulty: Optional[str] = Query(None, description="Easy | Medium | Hard"),
    min_quality: float = Query(6.0, ge=0, le=10, description="Minimum quality score"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    Browse the community question pool. Only approved questions are returned.
    Sorted by quality score descending.
    """
    questions = [
        q for q in _question_pool.values()
        if q.approved
        and q.quality_score >= min_quality
        and (mode is None or q.mode == mode)
        and (category is None or q.category.lower() == category.lower())
        and (difficulty is None or q.difficulty.lower() == difficulty.lower())
    ]

    # Sort by quality descending
    questions.sort(key=lambda q: q.quality_score, reverse=True)
    total = len(questions)
    page = questions[offset:offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "questions": [q.model_dump() for q in page],
    }


@router.get("/questions/pool/{question_id}")
async def get_community_question(question_id: str):
    """Retrieve a single community question by ID."""
    q = _question_pool.get(question_id)
    if not q or not q.approved:
        raise HTTPException(404, "Question not found or not yet approved.")
    return q.model_dump()


@router.post("/questions/pool/{question_id}/attempt")
async def record_attempt(
    question_id: str,
    score: float = Query(..., ge=0, le=10, description="Score achieved on this question (0–10)"),
):
    """
    Record a candidate's attempt on a community question.
    Updates the Elo-style difficulty rating and average score.
    Simple ELO: if score > 7, question is 'easier' → difficulty rating decreases.
    """
    q = _question_pool.get(question_id)
    if not q or not q.approved:
        raise HTTPException(404, "Question not found.")

    # ELO update (simplified)
    K = 32
    expected = 1 / (1 + 10 ** ((score * 100 - q.elo_difficulty) / 400))
    actual = 1 if score < 6 else 0  # candidate struggled → question is hard
    q.elo_difficulty = round(q.elo_difficulty + K * (actual - expected), 1)
    q.attempt_count += 1
    q.avg_score = round(
        ((q.avg_score or score) * (q.attempt_count - 1) + score) / q.attempt_count, 2
    )

    return {"question_id": question_id, "elo_difficulty": q.elo_difficulty, "avg_score": q.avg_score}
