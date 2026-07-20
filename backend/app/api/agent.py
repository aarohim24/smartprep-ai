"""
SmartPrep AI - Agent Decision API
POST /api/v1/agent/next-move
Decides whether to probe deeper, pivot, escalate, or advance after an answer.
"""
from fastapi import APIRouter, HTTPException
from app.models.schemas import AgentNextMoveRequest, AgentNextMoveResponse, AgentAction
from app.services.llm_service import llm_service
from app.services.session_store import session_store
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()


@router.post("/agent/next-move", response_model=AgentNextMoveResponse)
async def agent_next_move(request: AgentNextMoveRequest):
    """
    Agentic interviewer decision after evaluating a candidate's answer.
    The agent decides: probe_deeper | pivot | escalate | next_question
    based on rubric sub-scores and conversation history.
    """
    session = await session_store.get(request.session_id)
    if not session:
        raise HTTPException(404, "Session not found.")

    mode = (request.mode.value if request.mode else None) or "behavioral"

    try:
        result = await llm_service.decide_next_move(
            question=request.question,
            user_answer=request.user_answer,
            evaluation=request.evaluation.model_dump(),
            history=request.history or [],
            mode=mode,
        )
    except Exception as e:
        logger.error(f"Agent next-move failed: {e}", exc_info=True)
        # Graceful fallback: always safe to advance
        return AgentNextMoveResponse(
            action=AgentAction.next_question,
            follow_up_question=None,
            rationale="Agent decision unavailable — advancing to next question.",
        )

    action_str = result.get("action", "next_question")
    try:
        action = AgentAction(action_str)
    except ValueError:
        action = AgentAction.next_question

    return AgentNextMoveResponse(
        action=action,
        follow_up_question=result.get("follow_up_question"),
        rationale=result.get("rationale", ""),
        escalated_question=result.get("escalated_question"),
    )
