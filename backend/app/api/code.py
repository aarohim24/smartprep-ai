"""
SmartPrep AI - Code Execution API
Allows executing candidate code in an isolated Piston sandbox and
optionally grading it with the LLM (rubric + test case results).

Endpoints:
  POST /api/v1/code/execute   — Execute code and return stdout/stderr/exit code
  POST /api/v1/code/grade     — Execute + evaluate with LLM rubric
  GET  /api/v1/code/health    — Check if sandbox is reachable
  GET  /api/v1/code/languages — List supported languages
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.sandbox_service import execute_code, check_sandbox_health, LANGUAGE_VERSIONS
from app.services.llm_service import llm_service
from app.utils.logger import setup_logger
from app.utils.telemetry import telemetry

logger = setup_logger(__name__)
router = APIRouter()

SUPPORTED_LANGUAGES = list(LANGUAGE_VERSIONS.keys())


# ── Schemas ───────────────────────────────────────────────────────────────────

class TestCase(BaseModel):
    args: list = Field(default_factory=list)
    expected: object = None


class CodeExecuteRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=8000)
    language: str = Field(default="python")
    stdin: str = Field(default="")
    test_cases: Optional[List[TestCase]] = None
    entry_point: Optional[str] = None  # function name for test harness


class CodeGradeRequest(BaseModel):
    question: str = Field(..., min_length=5, description="The coding question/problem")
    code: str = Field(..., min_length=1, max_length=8000)
    language: str = Field(default="python")
    test_cases: Optional[List[TestCase]] = None
    entry_point: Optional[str] = None
    session_id: Optional[str] = None


class CodeExecuteResponse(BaseModel):
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    runtime_ms: Optional[float] = None
    test_results: Optional[list] = None
    passed: Optional[int] = None
    total: Optional[int] = None
    error: Optional[str] = None


class CodeGradeResponse(BaseModel):
    execution: CodeExecuteResponse
    score: float
    grade: str
    rubric_scores: Optional[dict] = None
    correctness_from_tests: Optional[float] = None
    feedback: str
    strengths: List[str] = []
    improvements: List[str] = []
    time_complexity: Optional[str] = None
    space_complexity: Optional[str] = None
    follow_up_question: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/code/execute", response_model=CodeExecuteResponse)
async def execute_code_endpoint(request: CodeExecuteRequest):
    """
    Execute code in the Piston sandbox.
    No LLM involved — pure execution with optional test harness.
    """
    if request.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            400,
            f"Unsupported language: {request.language}. "
            f"Supported: {', '.join(SUPPORTED_LANGUAGES)}"
        )

    test_cases_raw = (
        [tc.model_dump() for tc in request.test_cases] if request.test_cases else None
    )

    with telemetry.timer("code_execute"):
        result = await execute_code(
            code=request.code,
            language=request.language,
            stdin=request.stdin,
            test_cases=test_cases_raw,
            entry_point=request.entry_point,
        )

    if result.get("error") and not result.get("success"):
        # Surface sandbox-unavailable errors distinctly
        if "unavailable" in result["error"].lower():
            raise HTTPException(503, result["error"])

    return CodeExecuteResponse(**result)


@router.post("/code/grade", response_model=CodeGradeResponse)
async def grade_code_endpoint(request: CodeGradeRequest):
    """
    Execute code and grade it with the LLM rubric.
    Execution results (test pass/fail, runtime) inform the LLM's correctness score.
    """
    if request.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            400,
            f"Unsupported language: {request.language}. "
            f"Supported: {', '.join(SUPPORTED_LANGUAGES)}"
        )

    from app.utils.scoring import score_to_grade

    test_cases_raw = (
        [tc.model_dump() for tc in request.test_cases] if request.test_cases else None
    )

    # Step 1: Execute code in sandbox
    with telemetry.timer("code_execute"):
        execution = await execute_code(
            code=request.code,
            language=request.language,
            test_cases=test_cases_raw,
            entry_point=request.entry_point,
        )

    # Compute correctness signal from tests (0–10 scale)
    correctness_from_tests = None
    if execution.get("total") and execution["total"] > 0:
        correctness_from_tests = round((execution["passed"] / execution["total"]) * 10, 1)

    # Build execution context for LLM
    exec_summary = (
        f"Language: {request.language}\n"
        f"Exit code: {execution.get('exit_code', '?')}\n"
        f"Stdout: {execution.get('stdout', '')[:500]}\n"
        f"Stderr: {execution.get('stderr', '')[:300]}\n"
        f"Runtime: {execution.get('runtime_ms', 'unknown')}ms\n"
    )
    if correctness_from_tests is not None:
        exec_summary += (
            f"Test cases: {execution.get('passed', 0)}/{execution.get('total', 0)} passed "
            f"({correctness_from_tests:.1f}/10 correctness)\n"
        )

    # Step 2: LLM evaluation incorporating execution results
    with telemetry.timer("code_grade"):
        try:
            llm_result = await llm_service.evaluate_answer(
                question=request.question,
                user_answer=f"```{request.language}\n{request.code}\n```",
                resume_context=exec_summary,
                category="Coding",
                mode="coding",
                speech_metrics=None,
            )
        except Exception as e:
            logger.error(f"Code grading LLM call failed: {e}", exc_info=True)
            raise HTTPException(500, "LLM grading failed. Execution results are still available.")

    # Override correctness sub-score with test results if available
    rubric = llm_result.get("rubric_scores", {}) or {}
    if correctness_from_tests is not None:
        # Weight 60% test results, 40% LLM assessment for correctness
        llm_correctness = float(rubric.get("correctness", correctness_from_tests))
        rubric["correctness"] = round(0.6 * correctness_from_tests + 0.4 * llm_correctness, 1)

    score = float(llm_result.get("score", 5.0))
    if correctness_from_tests is not None and execution.get("total", 0) > 0:
        # Anchor overall score to test results (prevents hallucinated high scores for broken code)
        score = round(0.5 * score + 0.5 * correctness_from_tests, 1)

    score = max(0.0, min(10.0, score))
    grade = score_to_grade(score)

    exec_response = CodeExecuteResponse(**execution)

    return CodeGradeResponse(
        execution=exec_response,
        score=score,
        grade=grade,
        rubric_scores=rubric if rubric else None,
        correctness_from_tests=correctness_from_tests,
        feedback=llm_result.get("detailed_feedback", ""),
        strengths=llm_result.get("strengths", []),
        improvements=llm_result.get("improvements", []),
        time_complexity=None,   # Future: extract from LLM output
        space_complexity=None,
        follow_up_question=llm_result.get("follow_up_question"),
    )


@router.get("/code/health")
async def sandbox_health():
    """Check if the Piston sandbox container is reachable."""
    available = await check_sandbox_health()
    return {
        "sandbox_available": available,
        "sandbox_url": __import__("app.services.sandbox_service", fromlist=["PISTON_URL"]).PISTON_URL,
        "message": (
            "Sandbox is online and ready."
            if available
            else "Sandbox is offline. Run: docker compose --profile sandbox up -d"
        ),
    }


@router.get("/code/languages")
async def list_languages():
    """List supported programming languages and their pinned versions."""
    return {
        "languages": [
            {"language": lang, "version": ver}
            for lang, ver in LANGUAGE_VERSIONS.items()
        ]
    }
