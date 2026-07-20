"""
Unit tests for Pydantic schema validation.
Run: pytest tests/test_schemas.py -v
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pydantic import ValidationError
from app.models.schemas import (
    QuestionGenerationRequest,
    AnswerEvaluationRequest,
    EvaluationResponse,
    ExperienceLevel,
)


class TestQuestionGenerationRequest:

    def test_valid_request(self):
        req = QuestionGenerationRequest(
            session_id="abc-123",
            job_description="A" * 100,
            num_questions=7,
            experience_level="senior",
        )
        assert req.session_id == "abc-123"
        assert req.num_questions == 7
        assert req.experience_level == ExperienceLevel.senior

    def test_jd_too_short(self):
        with pytest.raises(ValidationError) as exc:
            QuestionGenerationRequest(
                session_id="abc",
                job_description="too short",
            )
        assert "min_length" in str(exc.value) or "50" in str(exc.value)

    def test_jd_too_long(self):
        with pytest.raises(ValidationError):
            QuestionGenerationRequest(
                session_id="abc",
                job_description="x" * 10001,
            )

    def test_num_questions_below_minimum(self):
        with pytest.raises(ValidationError):
            QuestionGenerationRequest(
                session_id="abc",
                job_description="A" * 100,
                num_questions=4,
            )

    def test_num_questions_above_maximum(self):
        with pytest.raises(ValidationError):
            QuestionGenerationRequest(
                session_id="abc",
                job_description="A" * 100,
                num_questions=11,
            )

    def test_invalid_experience_level(self):
        with pytest.raises(ValidationError):
            QuestionGenerationRequest(
                session_id="abc",
                job_description="A" * 100,
                experience_level="wizard",
            )

    def test_all_experience_levels_accepted(self):
        for level in ("junior", "mid", "senior", "lead"):
            req = QuestionGenerationRequest(
                session_id="abc",
                job_description="A" * 100,
                experience_level=level,
            )
            assert req.experience_level.value == level

    def test_focus_areas_optional(self):
        req = QuestionGenerationRequest(
            session_id="abc",
            job_description="A" * 100,
        )
        assert req.focus_areas is None

    def test_focus_areas_accepted(self):
        req = QuestionGenerationRequest(
            session_id="abc",
            job_description="A" * 100,
            focus_areas=["system design", "leadership"],
        )
        assert len(req.focus_areas) == 2


class TestAnswerEvaluationRequest:

    def test_valid_request(self):
        req = AnswerEvaluationRequest(
            session_id="abc-123",
            question="Tell me about yourself.",
            user_answer="I am a software engineer with 5 years of experience.",
        )
        assert req.session_id == "abc-123"

    def test_answer_too_short(self):
        with pytest.raises(ValidationError):
            AnswerEvaluationRequest(
                session_id="abc",
                question="Q?",
                user_answer="ok",
            )

    def test_answer_too_long(self):
        with pytest.raises(ValidationError):
            AnswerEvaluationRequest(
                session_id="abc",
                question="Q?",
                user_answer="x" * 8001,
            )

    def test_category_is_optional(self):
        req = AnswerEvaluationRequest(
            session_id="abc",
            question="Q?",
            user_answer="A valid answer that is long enough.",
        )
        assert req.category is None


class TestEvaluationResponse:

    def test_score_clamped_by_schema(self):
        """Score outside 0-10 should fail validation."""
        with pytest.raises(ValidationError):
            EvaluationResponse(
                score=11.0,
                grade="A",
                strengths=["good"],
                improvements=["better"],
                ideal_answer_points=["point"],
                detailed_feedback="feedback",
            )

    def test_negative_score_rejected(self):
        with pytest.raises(ValidationError):
            EvaluationResponse(
                score=-1.0,
                grade="F",
                strengths=[],
                improvements=[],
                ideal_answer_points=[],
                detailed_feedback="feedback",
            )

    def test_valid_response(self):
        resp = EvaluationResponse(
            score=7.5,
            grade="B",
            strengths=["Clear communication", "Good examples"],
            improvements=["More depth on X"],
            ideal_answer_points=["Cover A", "Mention B"],
            follow_up_question="Can you elaborate on X?",
            detailed_feedback="Overall a solid answer.",
        )
        assert resp.score == 7.5
        assert resp.grade == "B"
        assert resp.follow_up_question is not None
