"""
Integration tests for all API endpoints.
All services are mocked — no real OpenAI calls, no FAISS operations, no network.
Run: pytest tests/test_api.py -v
"""
import io
import json
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app

# ── Shared mock data ──────────────────────────────────────────────────────────

MOCK_SESSION_ID = "test-session-uuid-1234"

MOCK_RESUME_TEXT = "John Smith | john@example.com\n\nSenior Python Engineer with 6 years experience.\n" * 5

MOCK_QUESTIONS_RESULT = {
    "job_role": "Senior Backend Engineer",
    "key_requirements": ["Python", "FastAPI", "Distributed Systems"],
    "questions": [
        {
            "id": 1,
            "question": "Describe your experience with FastAPI.",
            "category": "Technical",
            "difficulty": "Medium",
            "rationale": "Core skill in JD",
        },
        {
            "id": 2,
            "question": "Tell me about a time you led a team.",
            "category": "Behavioral",
            "difficulty": "Medium",
            "rationale": "Leadership requirement",
        },
    ],
}

MOCK_EVALUATION_RESULT = {
    "score": 7.5,
    "grade": "B",
    "strengths": ["Good structure", "Clear examples"],
    "improvements": ["More technical depth"],
    "ideal_answer_points": ["Mention X", "Cover Y"],
    "follow_up_question": "Can you elaborate?",
    "detailed_feedback": "Solid answer overall.",
}

MOCK_SKILLS = ["Python", "FastAPI", "PostgreSQL", "Docker"]


# ── Client fixture ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """
    Sync TestClient. Startup events do NOT run (no context manager),
    so sys.exit() in startup_event is never triggered.
    """
    return TestClient(app, raise_server_exceptions=True)


# ── Service mock fixture ──────────────────────────────────────────────────────

@pytest.fixture
def mock_all(client):
    """Patch every external service for a clean, offline test run."""
    with (
        patch("app.api.resume.resume_parser") as mock_parser,
        patch("app.api.resume.rag_service") as mock_rag_r,
        patch("app.api.resume.llm_service") as mock_llm_r,
        patch("app.api.resume.session_store") as mock_store_r,
        patch("app.api.questions.rag_service") as mock_rag_q,
        patch("app.api.questions.llm_service") as mock_llm_q,
        patch("app.api.questions.session_store") as mock_store_q,
        patch("app.api.evaluation.rag_service") as mock_rag_e,
        patch("app.api.evaluation.llm_service") as mock_llm_e,
        patch("app.api.evaluation.session_store") as mock_store_e,
    ):
        # Resume endpoint
        mock_parser.extract_text.return_value = MOCK_RESUME_TEXT
        mock_rag_r.index_document = AsyncMock(return_value=5)
        mock_llm_r.extract_skills = AsyncMock(return_value=MOCK_SKILLS)
        mock_store_r.create = AsyncMock()

        # Questions endpoint
        mock_store_q.get = AsyncMock(return_value={
            "resume_text": MOCK_RESUME_TEXT,
            "skills": MOCK_SKILLS,
        })
        mock_rag_q.session_exists.return_value = True
        mock_rag_q.index_job_description = AsyncMock(return_value=3)
        mock_rag_q.retrieve_for_questions = AsyncMock(
            return_value="[RESUME] Python expert.\n\n[JD] Needs Python."
        )
        mock_llm_q.generate_questions = AsyncMock(return_value=MOCK_QUESTIONS_RESULT)
        mock_store_q.update = AsyncMock()

        # Evaluation endpoint
        mock_store_e.get = AsyncMock(return_value={
            "resume_text": MOCK_RESUME_TEXT,
            "skills": MOCK_SKILLS,
        })
        mock_rag_e.retrieve_for_evaluation = AsyncMock(
            return_value="[RESUME] FastAPI experience."
        )
        mock_llm_e.evaluate_answer = AsyncMock(return_value=MOCK_EVALUATION_RESULT)

        yield {
            "parser": mock_parser,
            "rag_resume": mock_rag_r,
            "llm_resume": mock_llm_r,
            "store_resume": mock_store_r,
            "rag_questions": mock_rag_q,
            "llm_questions": mock_llm_q,
            "store_questions": mock_store_q,
            "rag_eval": mock_rag_e,
            "llm_eval": mock_llm_e,
            "store_eval": mock_store_e,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def upload_file(client, content=b"x" * 300, filename="resume.pdf"):
    return client.post(
        "/api/v1/upload-resume",
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
    )


def generate_questions(client, session_id=MOCK_SESSION_ID, jd=None, num=7, level="senior"):
    return client.post("/api/v1/generate-questions", json={
        "session_id": session_id,
        "job_description": jd or ("We need a Senior Python Engineer with FastAPI " * 5),
        "num_questions": num,
        "experience_level": level,
    })


def evaluate_answer(client, session_id=MOCK_SESSION_ID, answer=None):
    return client.post("/api/v1/evaluate-answer", json={
        "session_id": session_id,
        "question": "Describe your FastAPI experience.",
        "user_answer": answer or "I have used FastAPI for 3 years building production REST APIs with async endpoints.",
        "category": "Technical",
    })


# ── Health ─────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"


# ── Resume Upload ──────────────────────────────────────────────────────────────

class TestResumeUpload:

    def test_valid_pdf_returns_200(self, client, mock_all):
        r = upload_file(client)
        assert r.status_code == 200
        d = r.json()
        assert "session_id" in d
        assert d["chunk_count"] == 5
        assert d["skills_detected"] == MOCK_SKILLS
        assert len(d["session_id"]) > 0

    def test_empty_file_returns_400(self, client, mock_all):
        r = upload_file(client, content=b"")
        assert r.status_code == 400

    def test_unsupported_extension_returns_400(self, client, mock_all):
        r = upload_file(client, filename="resume.docx")
        assert r.status_code == 400

    def test_oversized_file_returns_413(self, client, mock_all):
        r = upload_file(client, content=b"x" * (11 * 1024 * 1024))
        assert r.status_code == 413

    def test_txt_file_accepted(self, client, mock_all):
        r = upload_file(client, filename="resume.txt")
        assert r.status_code == 200

    def test_md_file_accepted(self, client, mock_all):
        r = upload_file(client, filename="resume.md")
        assert r.status_code == 200

    def test_short_extracted_text_returns_422(self, client, mock_all):
        mock_all["parser"].extract_text.return_value = "too short"
        r = upload_file(client)
        assert r.status_code == 422

    def test_parser_exception_returns_500_without_leaking_detail(self, client, mock_all):
        mock_all["parser"].extract_text.side_effect = RuntimeError("secret internal error xyz")
        r = upload_file(client)
        assert r.status_code == 500
        assert "secret" not in r.json().get("detail", "")
        assert "internal error xyz" not in r.json().get("detail", "")

    def test_rag_failure_returns_500(self, client, mock_all):
        mock_all["rag_resume"].index_document = AsyncMock(
            side_effect=Exception("faiss broken")
        )
        r = upload_file(client)
        assert r.status_code == 500
        assert "faiss broken" not in r.json().get("detail", "")

    def test_skill_extraction_failure_still_returns_200(self, client, mock_all):
        """Skill extraction is non-fatal — upload should still succeed."""
        mock_all["llm_resume"].extract_skills = AsyncMock(
            side_effect=Exception("openai down")
        )
        r = upload_file(client)
        assert r.status_code == 200
        assert r.json()["skills_detected"] == []


# ── Generate Questions ─────────────────────────────────────────────────────────

class TestGenerateQuestions:

    def test_valid_request_returns_200(self, client, mock_all):
        r = generate_questions(client)
        assert r.status_code == 200
        d = r.json()
        assert d["job_role"] == "Senior Backend Engineer"
        assert len(d["questions"]) == 2
        assert d["questions"][0]["category"] == "Technical"
        assert len(d["key_requirements"]) == 3

    def test_session_not_found_returns_404(self, client, mock_all):
        mock_all["store_questions"].get = AsyncMock(return_value=None)
        r = generate_questions(client)
        assert r.status_code == 404

    def test_jd_too_short_returns_422(self, client, mock_all):
        r = client.post("/api/v1/generate-questions", json={
            "session_id": MOCK_SESSION_ID,
            "job_description": "short",
            "num_questions": 7,
            "experience_level": "mid",
        })
        assert r.status_code == 422

    def test_jd_too_long_returns_422(self, client, mock_all):
        r = client.post("/api/v1/generate-questions", json={
            "session_id": MOCK_SESSION_ID,
            "job_description": "x" * 10001,
            "num_questions": 7,
            "experience_level": "mid",
        })
        assert r.status_code == 422

    def test_num_questions_below_min_returns_422(self, client, mock_all):
        r = client.post("/api/v1/generate-questions", json={
            "session_id": MOCK_SESSION_ID,
            "job_description": "x" * 200,
            "num_questions": 4,
            "experience_level": "mid",
        })
        assert r.status_code == 422

    def test_num_questions_above_max_returns_422(self, client, mock_all):
        r = client.post("/api/v1/generate-questions", json={
            "session_id": MOCK_SESSION_ID,
            "job_description": "x" * 200,
            "num_questions": 11,
            "experience_level": "mid",
        })
        assert r.status_code == 422

    def test_invalid_experience_level_returns_422(self, client, mock_all):
        r = client.post("/api/v1/generate-questions", json={
            "session_id": MOCK_SESSION_ID,
            "job_description": "x" * 200,
            "num_questions": 7,
            "experience_level": "wizard",
        })
        assert r.status_code == 422

    def test_llm_failure_returns_500_without_leaking(self, client, mock_all):
        mock_all["llm_questions"].generate_questions = AsyncMock(
            side_effect=Exception("secret openai key exposed")
        )
        r = generate_questions(client)
        assert r.status_code == 500
        assert "secret" not in r.json().get("detail", "")

    def test_all_experience_levels_accepted(self, client, mock_all):
        for level in ("junior", "mid", "senior", "lead"):
            r = generate_questions(client, level=level)
            assert r.status_code == 200, f"Failed for level: {level}"


# ── Evaluate Answer ────────────────────────────────────────────────────────────

class TestEvaluateAnswer:

    def test_valid_returns_200_with_all_fields(self, client, mock_all):
        r = evaluate_answer(client)
        assert r.status_code == 200
        d = r.json()
        assert d["score"] == 7.5
        assert d["grade"] == "B"
        assert len(d["strengths"]) > 0
        assert len(d["improvements"]) > 0
        assert len(d["ideal_answer_points"]) > 0
        assert d["follow_up_question"] is not None
        assert len(d["detailed_feedback"]) > 0

    def test_session_not_found_returns_404(self, client, mock_all):
        mock_all["store_eval"].get = AsyncMock(return_value=None)
        r = evaluate_answer(client)
        assert r.status_code == 404

    def test_answer_too_short_returns_422(self, client, mock_all):
        r = evaluate_answer(client, answer="ok")
        assert r.status_code == 422

    def test_answer_too_long_returns_422(self, client, mock_all):
        r = evaluate_answer(client, answer="x" * 8001)
        assert r.status_code == 422

    def test_out_of_bounds_score_is_clamped(self, client, mock_all):
        mock_all["llm_eval"].evaluate_answer = AsyncMock(return_value={
            **MOCK_EVALUATION_RESULT,
            "score": 15.0,
        })
        r = evaluate_answer(client)
        assert r.status_code == 200
        assert r.json()["score"] <= 10.0

    def test_negative_score_is_clamped(self, client, mock_all):
        mock_all["llm_eval"].evaluate_answer = AsyncMock(return_value={
            **MOCK_EVALUATION_RESULT,
            "score": -3.0,
        })
        r = evaluate_answer(client)
        assert r.status_code == 200
        assert r.json()["score"] >= 0.0

    def test_llm_failure_returns_500_without_leaking(self, client, mock_all):
        mock_all["llm_eval"].evaluate_answer = AsyncMock(
            side_effect=Exception("secret token leak abc")
        )
        r = evaluate_answer(client)
        assert r.status_code == 500
        assert "secret" not in r.json().get("detail", "")

    def test_rag_failure_falls_back_gracefully(self, client, mock_all):
        """RAG failure should fall back to raw resume, not crash."""
        mock_all["rag_eval"].retrieve_for_evaluation = AsyncMock(
            side_effect=Exception("faiss error")
        )
        r = evaluate_answer(client)
        # Should still call LLM with the raw resume fallback
        assert r.status_code == 200


# ── Score-to-grade helper ──────────────────────────────────────────────────────

class TestScoreToGrade:
    def test_grade_boundaries(self):
        from app.utils.scoring import score_to_grade as _score_to_grade
        assert _score_to_grade(9.0) == "A+"
        assert _score_to_grade(9.5) == "A+"
        assert _score_to_grade(8.0) == "A"
        assert _score_to_grade(8.9) == "A"
        assert _score_to_grade(7.0) == "B"
        assert _score_to_grade(7.9) == "B"
        assert _score_to_grade(6.0) == "C"
        assert _score_to_grade(6.9) == "C"
        assert _score_to_grade(5.0) == "D"
        assert _score_to_grade(5.9) == "D"
        assert _score_to_grade(4.9) == "F"
        assert _score_to_grade(0.0) == "F"

