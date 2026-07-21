"""
SmartPrep AI - LLM Service
Uses Groq (free) via OpenAI-compatible client.
Supports mode-aware question generation, 4-dimension rubric evaluation,
confidence-aware grading, provenance tracing, and agentic follow-up decisions.
"""
import json
from typing import List, Optional

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import openai

from app.utils.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Groq uses OpenAI-compatible API — just swap the base_url and key
client = AsyncOpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

MAX_RESUME_CONTEXT_CHARS = 3000
MAX_JD_CHARS = 2000
MAX_ANSWER_CHARS = 4000

# ── Mode Personas ──────────────────────────────────────────────────────────────

MODE_PERSONAS = {
    "coding": (
        "You are a senior software engineer at a top-tier tech company conducting a coding interview. "
        "You focus on algorithmic thinking, code correctness, time/space complexity, edge cases, "
        "and clean implementation. You ask candidates to explain their approach before coding, "
        "then probe their solution."
    ),
    "system_design": (
        "You are a Staff Engineer conducting a system design interview. "
        "You evaluate candidates on their ability to scope requirements, design scalable distributed systems, "
        "reason about trade-offs (SQL vs NoSQL, sync vs async, CAP theorem), "
        "and communicate architecture decisions clearly."
    ),
    "behavioral": (
        "You are a senior hiring manager conducting a behavioral interview. "
        "You use the STAR method (Situation, Task, Action, Result) to evaluate responses. "
        "You focus on leadership, collaboration, conflict resolution, ownership, and growth mindset."
    ),
}

TIER_MIX = {
    "easy": "Focus 70% on foundational concepts and 30% on slightly harder application questions. "
             "Avoid trick questions or niche edge cases.",
    "mixed": "Mix difficulty: 30% easy warm-up, 40% medium core, 30% hard stretch questions.",
    "hard": "Focus on hard, expert-level questions requiring deep technical knowledge, "
             "system-level reasoning, or complex behavioral scenarios. No easy warm-ups.",
}

# ── Question Generation ────────────────────────────────────────────────────────

QUESTION_GENERATION_SYSTEM = """You are an expert technical recruiter and interview coach with 15+ years of experience.
Your task is to generate highly tailored, insightful interview questions based on:
1. The candidate's resume and skills (retrieved context)
2. The target job description
3. The experience level and interview mode

Rules:
- Questions must be SPECIFIC to the candidate's background, not generic
- Respect the mode persona and tier difficulty mix provided
- Reference specific technologies, projects, or experiences from the resume
- Calibrate difficulty to the experience level
- Each question should have a clear purpose tied to job requirements

Return ONLY valid JSON. No markdown, no explanations outside JSON."""

QUESTION_GENERATION_USER = """
MODE: {mode}
MODE PERSONA: {mode_persona}
DIFFICULTY TIER: {tier}
TIER GUIDANCE: {tier_guidance}

CANDIDATE CONTEXT (from resume):
{resume_context}

JOB DESCRIPTION:
{job_description}

EXPERIENCE LEVEL: {experience_level}
NUMBER OF QUESTIONS: {num_questions}
{focus_areas_text}

Generate {num_questions} tailored interview questions matching the mode and tier. Return JSON in this exact format:
{{
  "job_role": "detected role title",
  "key_requirements": ["req1", "req2", "req3", "req4", "req5"],
  "questions": [
    {{
      "id": 1,
      "question": "specific question text",
      "category": "Technical|Behavioral|Situational|Culture-fit|System Design|Coding",
      "difficulty": "Easy|Medium|Hard",
      "rationale": "why this question tests a key requirement"
    }}
  ]
}}"""

# ── Evaluation Prompts ─────────────────────────────────────────────────────────

EVALUATION_SYSTEM_BASE = """You are a senior hiring manager and technical interviewer evaluating a candidate's answer.
Provide rigorous, constructive, and specific feedback with a 4-dimension rubric.

RUBRIC DIMENSIONS (each scored 0–10):
- correctness: Factual/technical accuracy. Are claims correct? Is the approach sound?
- completeness: Coverage of key points. Did they address the full question scope?
- communication: Clarity, structure, conciseness. Is it well-organized and easy to follow?
- problem_solving: Depth of reasoning, edge-case awareness, trade-off analysis.

OVERALL SCORE: weighted average of the 4 dimensions (you choose weights based on question type).

CONFIDENCE: Emit a confidence_score (0–1) reflecting how certain you are in your assessment.
  - Set low_confidence_flag=true if confidence_score < 0.6 (insufficient answer detail, ambiguous question, etc.)

PROVENANCE: List 1–3 short excerpts from the CANDIDATE CONTEXT that most influenced your score.
  If context is empty, set provenance to [].

Scoring guide:
- 9-10: Exceptional — comprehensive, specific, shows deep expertise
- 7-8: Strong — covers key points with good depth
- 5-6: Adequate — hits basics but lacks depth or specificity
- 3-4: Weak — superficial or missing critical points
- 0-2: Poor — incorrect, incoherent, or irrelevant

Return ONLY valid JSON. No markdown, no explanations outside JSON."""

EVALUATION_MODE_ADDENDUM = {
    "coding": (
        "\nFor CODING questions: weight correctness=0.4, completeness=0.25, "
        "communication=0.15, problem_solving=0.2. "
        "Check: does the algorithm handle edge cases? Is complexity discussed?"
    ),
    "system_design": (
        "\nFor SYSTEM DESIGN questions: weight correctness=0.2, completeness=0.3, "
        "communication=0.2, problem_solving=0.3. "
        "Check: are trade-offs articulated? Is the design scalable?"
    ),
    "behavioral": (
        "\nFor BEHAVIORAL questions: weight correctness=0.15, completeness=0.25, "
        "communication=0.35, problem_solving=0.25. "
        "Check: does the answer follow STAR structure (Situation, Task, Action, Result)?"
    ),
}

EVALUATION_USER = """
INTERVIEW QUESTION: {question}
QUESTION CATEGORY: {category}
INTERVIEW MODE: {mode}

CANDIDATE'S RESUME CONTEXT:
{resume_context}

CANDIDATE'S ANSWER:
{user_answer}
{speech_section}
Evaluate this answer and return JSON in this exact format:
{{
  "score": <float 0-10>,
  "grade": "<A|B|C|D|F>",
  "rubric_scores": {{
    "correctness": <float 0-10>,
    "completeness": <float 0-10>,
    "communication": <float 0-10>,
    "problem_solving": <float 0-10>
  }},
  "confidence_score": <float 0-1>,
  "low_confidence_flag": <true|false>,
  "provenance": ["excerpt1 from context", "excerpt2 from context"],
  "strengths": ["strength1", "strength2", "strength3"],
  "improvements": ["improvement1", "improvement2", "improvement3"],
  "ideal_answer_points": ["key point 1", "key point 2", "key point 3", "key point 4"],
  "follow_up_question": "a natural follow-up question based on their answer",
  "detailed_feedback": "2-3 sentence comprehensive feedback paragraph"
}}"""

# ── Agent Decision Prompts ─────────────────────────────────────────────────────

AGENT_SYSTEM = """You are an expert interviewer agent. After receiving a candidate's evaluated answer,
you decide the optimal next move in the interview:

- probe_deeper: Answer shows partial understanding; dig deeper on a specific weak point
- pivot: Communication or approach was poor; reframe the topic from a different angle
- escalate: Answer was strong (score >= 8); present a harder follow-up challenge
- next_question: Answer was adequate; move to the next prepared question

Base your decision on the rubric sub-scores:
- If correctness < 6 or completeness < 6 → probe_deeper
- If communication < 5 → pivot
- If overall score >= 8 → escalate
- Otherwise → next_question

Return ONLY valid JSON."""

AGENT_USER = """
QUESTION ASKED: {question}
CANDIDATE'S ANSWER: {user_answer}

EVALUATION SCORES:
- Overall: {overall_score}/10
- Correctness: {correctness}/10
- Completeness: {completeness}/10
- Communication: {communication}/10
- Problem Solving: {problem_solving}/10

INTERVIEW MODE: {mode}
CONVERSATION HISTORY (last 3 turns): {history_summary}

Decide the next move and return JSON:
{{
  "action": "<probe_deeper|pivot|escalate|next_question>",
  "follow_up_question": "<question to ask if action is probe_deeper or pivot, else null>",
  "escalated_question": "<harder follow-up if action is escalate, else null>",
  "rationale": "1-sentence explanation of why this move was chosen"
}}"""

# ── Query Rewriting ────────────────────────────────────────────────────────────

QUERY_REWRITE_SYSTEM = """You are a retrieval assistant. Given a candidate's answer that may be multi-part
or ambiguous, rewrite it into 1-3 focused search queries that will retrieve the most relevant resume
context for grading. Return ONLY valid JSON: {"queries": ["query1", "query2"]}"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _openai_retry():
    return retry(
        retry=retry_if_exception_type((
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.InternalServerError,
        )),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )


def _truncate_at_sentence(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    for sep in (". ", ".\n", "! ", "? "):
        idx = truncated.rfind(sep)
        if idx > max_chars * 0.5:
            return truncated[:idx + 1]
    return truncated


def _build_eval_system(mode: Optional[str]) -> str:
    addendum = EVALUATION_MODE_ADDENDUM.get(mode or "behavioral", "")
    return EVALUATION_SYSTEM_BASE + addendum


def _build_speech_section(speech_metrics) -> str:
    if not speech_metrics:
        return ""
    return (
        f"\nSPEECH METRICS (captured during answer):\n"
        f"- Filler words (um/uh/like): {speech_metrics.filler_word_count}\n"
        f"- Speaking pace: {speech_metrics.wpm:.0f} WPM\n"
        f"- Significant pauses: {speech_metrics.pause_count}\n"
        f"(Factor filler words and pacing into the communication sub-score.)\n"
    )


# ── Service ────────────────────────────────────────────────────────────────────

class LLMService:
    def __init__(self):
        self.model = settings.GROQ_MODEL
        self.temperature = 0.7

    @_openai_retry()
    async def generate_questions(
        self,
        resume_context: str,
        job_description: str,
        experience_level: str,
        num_questions: int,
        focus_areas: Optional[List[str]] = None,
        mode: str = "behavioral",
        tier: str = "mixed",
    ) -> dict:
        focus_text = f"FOCUS AREAS: {', '.join(focus_areas)}" if focus_areas else ""

        user_prompt = QUESTION_GENERATION_USER.format(
            mode=mode.upper(),
            mode_persona=MODE_PERSONAS.get(mode, MODE_PERSONAS["behavioral"]),
            tier=tier.upper(),
            tier_guidance=TIER_MIX.get(tier, TIER_MIX["mixed"]),
            resume_context=_truncate_at_sentence(resume_context, MAX_RESUME_CONTEXT_CHARS),
            job_description=_truncate_at_sentence(job_description, MAX_JD_CHARS),
            experience_level=experience_level,
            num_questions=num_questions,
            focus_areas_text=focus_text,
        )

        logger.info(f"Generating {num_questions} questions via Groq ({self.model}) — mode={mode}, tier={tier}")

        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": QUESTION_GENERATION_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            max_tokens=1800,  # 7 questions * ~200 tokens each fits well within 1800
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        logger.info(f"Generated {len(result.get('questions', []))} questions")
        return result

    @_openai_retry()
    async def evaluate_answer(
        self,
        question: str,
        user_answer: str,
        resume_context: str,
        category: str = "General",
        mode: str = "behavioral",
        speech_metrics=None,
    ) -> dict:
        user_prompt = EVALUATION_USER.format(
            question=question,
            category=category,
            mode=mode.upper(),
            resume_context=_truncate_at_sentence(resume_context, MAX_RESUME_CONTEXT_CHARS),
            user_answer=_truncate_at_sentence(user_answer, MAX_ANSWER_CHARS),
            speech_section=_build_speech_section(speech_metrics),
        )

        system_prompt = _build_eval_system(mode)

        logger.info(f"Evaluating answer via Groq ({self.model}) — mode={mode}")

        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        logger.info(f"Evaluation complete. Score: {result.get('score')}, Confidence: {result.get('confidence_score')}")
        return result

    @_openai_retry()
    async def decide_next_move(
        self,
        question: str,
        user_answer: str,
        evaluation: dict,
        history: Optional[List[dict]] = None,
        mode: str = "behavioral",
    ) -> dict:
        rubric = evaluation.get("rubric_scores", {})
        history_summary = ""
        if history:
            recent = history[-3:]
            history_summary = "; ".join(
                f"Q: {t.get('question', '')[:60]}... → score {t.get('score', '?')}"
                for t in recent
            )

        user_prompt = AGENT_USER.format(
            question=question,
            user_answer=_truncate_at_sentence(user_answer, 1000),
            overall_score=evaluation.get("score", 5),
            correctness=rubric.get("correctness", 5),
            completeness=rubric.get("completeness", 5),
            communication=rubric.get("communication", 5),
            problem_solving=rubric.get("problem_solving", 5),
            mode=mode.upper(),
            history_summary=history_summary or "No prior turns",
        )

        logger.info(f"Agent deciding next move — mode={mode}")

        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": AGENT_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=600,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        logger.info(f"Agent action: {result.get('action')}")
        return result

    @_openai_retry()
    async def rewrite_query_for_retrieval(self, answer_text: str) -> List[str]:
        """Decompose a multi-part answer into focused retrieval queries."""
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": QUERY_REWRITE_SYSTEM},
                {"role": "user", "content": f"Answer to decompose:\n{_truncate_at_sentence(answer_text, 1000)}"},
            ],
            temperature=0.1,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("queries", [answer_text[:200]])

    @_openai_retry()
    async def extract_skills(self, resume_text: str) -> List[str]:
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": 'Extract technical and soft skills from the resume. Return JSON: {"skills": ["skill1", "skill2", ...]}. Max 20 skills. Only return JSON.'
                },
                {
                    "role": "user",
                    "content": f"Extract skills from this resume:\n\n{_truncate_at_sentence(resume_text, MAX_RESUME_CONTEXT_CHARS)}"
                },
            ],
            temperature=0.1,
            max_tokens=250,  # 20 skills * ~10 tokens each; 250 is plenty
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("skills", [])

    @_openai_retry()
    async def generate_debrief_summary(
        self,
        mode: str,
        tier: str,
        results: List[dict],
        avg_score: float,
    ) -> dict:
        """Generate natural-language debrief insights from session results."""
        results_summary = "\n".join(
            f"Q{r.get('question_id')}: [{r.get('category')}] score={r.get('score')}/10 — {r.get('question', '')[:80]}..."
            for r in results
        )

        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a career coach summarizing a mock interview session. "
                        "Based on the question results, generate: 3 strength highlights, "
                        "3 improvement areas, and a recommendation for next steps. "
                        "Return ONLY valid JSON: "
                        "{\"strengths_summary\": [...], \"improvement_focus\": [...], \"next_steps\": \"...\"}",
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Mode: {mode.upper()}, Tier: {tier.upper()}, Avg score: {avg_score:.1f}/10\n\n"
                        f"Results:\n{results_summary}"
                    ),
                },
            ],
            temperature=0.5,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)


llm_service = LLMService()
