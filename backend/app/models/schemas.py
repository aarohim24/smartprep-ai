"""
SmartPrep AI - Pydantic Data Models
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class ExperienceLevel(str, Enum):
    junior = "junior"
    mid = "mid"
    senior = "senior"
    lead = "lead"


class SessionTier(str, Enum):
    easy = "easy"      # 5 questions, 15 min
    mixed = "mixed"    # 7 questions, 25 min
    hard = "hard"      # 10 questions, 35 min


class InterviewMode(str, Enum):
    coding = "coding"
    system_design = "system_design"
    behavioral = "behavioral"


# ── Resume Models ─────────────────────────────────────────────────────────────

class ResumeUploadResponse(BaseModel):
    session_id: str = Field(..., description="Unique session identifier for this resume")
    extracted_text: str = Field(..., description="Extracted text content from resume")
    chunk_count: int = Field(..., description="Number of chunks stored in vector DB")
    skills_detected: List[str] = Field(default=[], description="Detected skills from resume")
    message: str = "Resume processed and indexed successfully"


# ── Question Models ───────────────────────────────────────────────────────────

class QuestionGenerationRequest(BaseModel):
    session_id: str = Field(..., description="Session ID from resume upload")
    job_description: str = Field(..., min_length=50, max_length=10000, description="Target job description")
    num_questions: int = Field(default=7, ge=5, le=10, description="Number of questions (5-10)")
    experience_level: ExperienceLevel = Field(default=ExperienceLevel.mid)
    focus_areas: Optional[List[str]] = Field(
        default=None,
        description="Optional: specific areas to focus on (e.g., ['system design', 'leadership'])"
    )
    tier: Optional[SessionTier] = Field(default=SessionTier.mixed, description="Session difficulty tier")
    mode: Optional[InterviewMode] = Field(default=InterviewMode.behavioral, description="Interview mode")


class InterviewQuestion(BaseModel):
    id: int
    question: str
    category: str = Field(..., description="e.g., Technical, Behavioral, Situational")
    difficulty: str = Field(..., description="Easy / Medium / Hard")
    rationale: str = Field(..., description="Why this question was chosen")


class QuestionGenerationResponse(BaseModel):
    session_id: str
    questions: List[InterviewQuestion]
    job_role: str = Field(..., description="Detected job role from JD")
    key_requirements: List[str] = Field(..., description="Key requirements extracted from JD")
    tier: Optional[SessionTier] = None
    mode: Optional[InterviewMode] = None
    timer_seconds: Optional[int] = Field(None, description="Session timer duration in seconds")


# ── Evaluation Models ─────────────────────────────────────────────────────────

class SpeechMetrics(BaseModel):
    """Optional speech signal data captured by VoiceRecorder component."""
    filler_word_count: int = Field(default=0, description="Count of filler words (um, uh, like, etc.)")
    wpm: float = Field(default=0.0, description="Words per minute")
    pause_count: int = Field(default=0, description="Number of significant pauses (>2s)")


class AnswerEvaluationRequest(BaseModel):
    session_id: str = Field(..., description="Session ID for context retrieval")
    question: str = Field(..., max_length=2000, description="The interview question")
    user_answer: str = Field(..., min_length=10, max_length=8000, description="Candidate's answer")
    category: Optional[str] = Field(default=None, description="Question category for context")
    mode: Optional[InterviewMode] = Field(default=None, description="Interview mode for rubric selection")
    speech_metrics: Optional[SpeechMetrics] = Field(default=None, description="Optional speech signal data")


class RubricScores(BaseModel):
    """Decomposed rubric scores, each 0–10."""
    correctness: float = Field(..., ge=0, le=10, description="Factual accuracy and technical correctness")
    completeness: float = Field(..., ge=0, le=10, description="Coverage of key points")
    communication: float = Field(..., ge=0, le=10, description="Clarity, structure, and delivery")
    problem_solving: float = Field(..., ge=0, le=10, description="Approach, reasoning, and depth")


class EvaluationResponse(BaseModel):
    score: float = Field(..., ge=0, le=10, description="Overall score out of 10")
    grade: str = Field(..., description="A / B / C / D / F")
    rubric_scores: Optional[RubricScores] = Field(None, description="Decomposed rubric sub-scores")
    confidence_score: Optional[float] = Field(None, ge=0, le=1, description="Grader confidence (0–1)")
    low_confidence_flag: bool = Field(default=False, description="True if confidence < 0.6")
    provenance: Optional[List[str]] = Field(None, description="Retrieved chunks that drove the score")
    strengths: List[str] = Field(..., description="What the candidate did well")
    improvements: List[str] = Field(..., description="Areas to improve")
    ideal_answer_points: List[str] = Field(..., description="Key points of a strong answer")
    follow_up_question: Optional[str] = Field(None, description="Suggested follow-up")
    detailed_feedback: str = Field(..., description="Comprehensive paragraph feedback")


# ── Debrief Models ────────────────────────────────────────────────────────────

class QuestionResult(BaseModel):
    """Single question result for debrief submission."""
    question_id: int
    question: str
    category: str
    difficulty: str
    score: float
    rubric_scores: Optional[RubricScores] = None


class DebriefRequest(BaseModel):
    session_id: str
    mode: InterviewMode
    tier: SessionTier
    results: List[QuestionResult]
    time_used_seconds: Optional[int] = None


class CategoryBreakdown(BaseModel):
    category: str
    avg_score: float
    question_count: int
    rubric_avg: Optional[RubricScores] = None


class DebriefReport(BaseModel):
    session_id: str
    overall_score: float
    grade: str
    tier: SessionTier
    mode: InterviewMode
    time_used_seconds: Optional[int] = None
    category_breakdown: List[CategoryBreakdown]
    strengths_summary: List[str]
    revisit_list: List[str]           # questions to revisit
    suggested_next_tier: SessionTier
    improvement_focus: List[str]      # top 3 improvement areas
    completion_rate: float            # fraction of questions answered


# ── Agent Models ──────────────────────────────────────────────────────────────

class AgentAction(str, Enum):
    probe_deeper = "probe_deeper"
    pivot = "pivot"
    escalate = "escalate"
    next_question = "next_question"


class AgentNextMoveRequest(BaseModel):
    session_id: str
    question: str
    user_answer: str
    evaluation: EvaluationResponse
    history: Optional[List[dict]] = Field(default=[], description="Previous Q&A turns this session")
    mode: Optional[InterviewMode] = None


class AgentNextMoveResponse(BaseModel):
    action: AgentAction
    follow_up_question: Optional[str] = None
    rationale: str
    escalated_question: Optional[str] = None


# ── Session Models ────────────────────────────────────────────────────────────

class SessionContext(BaseModel):
    session_id: str
    resume_text: str
    skills: List[str]
    job_description: Optional[str] = None
    questions: Optional[List[InterviewQuestion]] = None
    tier: Optional[SessionTier] = None
    mode: Optional[InterviewMode] = None
