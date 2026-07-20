"""
SmartPrep AI - Question Validator Agent
Multi-step agent that checks user-submitted prep questions for:
1. Answerability — can the question be meaningfully answered?
2. Difficulty accuracy — does the stated difficulty match the question?
3. Duplicate detection — is this already in the pool (semantic similarity)?
4. Quality scoring — overall quality signal

Returns a structured verdict with suggested edits if needed.
"""
import json
from typing import Optional, List
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import openai

from app.utils.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

client = AsyncOpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

# ── Prompts ────────────────────────────────────────────────────────────────────

VALIDATOR_SYSTEM = """You are a question quality validator for a technical interview prep platform.
Evaluate submitted questions across 4 dimensions and return a structured verdict.
Return ONLY valid JSON. No markdown, no explanations outside JSON."""

ANSWERABILITY_CHECK = """
QUESTION: {question}
CATEGORY: {category}
DIFFICULTY: {difficulty}

Check if this question is answerable by a software engineering candidate:
- Is it clear and unambiguous?
- Does it have a reasonable expected answer?
- Is it appropriate for a technical interview?

Return JSON: {{
  "answerable": true|false,
  "reason": "1 sentence explanation",
  "suggested_rewrite": "improved version if not answerable, else null"
}}"""

DIFFICULTY_CHECK = """
QUESTION: {question}
CATEGORY: {category}
STATED_DIFFICULTY: {difficulty}

Assess whether the stated difficulty (Easy/Medium/Hard) matches the actual complexity:
- Easy: foundational, expected of juniors
- Medium: requires solid experience, mid-level engineers
- Hard: expert-level, requires deep knowledge or experience

Return JSON: {{
  "difficulty_accurate": true|false,
  "suggested_difficulty": "Easy|Medium|Hard",
  "reason": "1 sentence"
}}"""

QUALITY_SCORE_CHECK = """
QUESTION: {question}
CATEGORY: {category}
DIFFICULTY: {difficulty}

Score this interview question on overall quality (0–10):
- 9-10: Excellent — specific, tests real skill, clear expected answer
- 7-8: Good — tests relevant skill, minor clarity issues
- 5-6: Average — too generic or could be better focused
- 3-4: Below average — vague, unfocused, or off-topic
- 0-2: Poor — not suitable for interview prep

Return JSON: {{
  "quality_score": <float 0-10>,
  "strengths": ["str1", "str2"],
  "weaknesses": ["str1", "str2"],
  "suggested_edit": "improved question text, or null if already good"
}}"""


def _openai_retry():
    return retry(
        retry=retry_if_exception_type((
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.InternalServerError,
        )),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        stop=stop_after_attempt(3),
        reraise=True,
    )


class ValidatorAgent:
    """
    Multi-step question validation agent.
    Each step is a focused LLM call; results are aggregated into a verdict.
    """

    def __init__(self):
        self.model = settings.GROQ_MODEL

    @_openai_retry()
    async def _call(self, prompt: str, system: str = VALIDATOR_SYSTEM) -> dict:
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)

    async def check_answerability(self, question: str, category: str, difficulty: str) -> dict:
        prompt = ANSWERABILITY_CHECK.format(
            question=question, category=category, difficulty=difficulty
        )
        try:
            result = await self._call(prompt)
            return {
                "pass": result.get("answerable", True),
                "reason": result.get("reason", ""),
                "suggested_rewrite": result.get("suggested_rewrite"),
            }
        except Exception as e:
            logger.warning(f"Answerability check failed: {e}")
            return {"pass": True, "reason": "Check unavailable", "suggested_rewrite": None}

    async def check_difficulty_accuracy(self, question: str, category: str, difficulty: str) -> dict:
        prompt = DIFFICULTY_CHECK.format(
            question=question, category=category, difficulty=difficulty
        )
        try:
            result = await self._call(prompt)
            return {
                "accurate": result.get("difficulty_accurate", True),
                "suggested_difficulty": result.get("suggested_difficulty", difficulty),
                "reason": result.get("reason", ""),
            }
        except Exception as e:
            logger.warning(f"Difficulty check failed: {e}")
            return {"accurate": True, "suggested_difficulty": difficulty, "reason": "Check unavailable"}

    async def check_quality(self, question: str, category: str, difficulty: str) -> dict:
        prompt = QUALITY_SCORE_CHECK.format(
            question=question, category=category, difficulty=difficulty
        )
        try:
            result = await self._call(prompt)
            return {
                "quality_score": max(0.0, min(10.0, float(result.get("quality_score", 7.0)))),
                "strengths": result.get("strengths", []),
                "weaknesses": result.get("weaknesses", []),
                "suggested_edit": result.get("suggested_edit"),
            }
        except Exception as e:
            logger.warning(f"Quality check failed: {e}")
            return {"quality_score": 7.0, "strengths": [], "weaknesses": [], "suggested_edit": None}

    async def check_duplicate(
        self,
        question: str,
        existing_questions: Optional[List[str]] = None,
    ) -> dict:
        """
        Simple duplicate check: keyword overlap heuristic.
        For production, replace with embedding cosine similarity against the pool.
        """
        if not existing_questions:
            return {"is_duplicate": False, "similar_question": None, "similarity": 0.0}

        q_tokens = set(question.lower().split())
        best_match = None
        best_score = 0.0

        for existing in existing_questions:
            e_tokens = set(existing.lower().split())
            if not e_tokens:
                continue
            intersection = q_tokens & e_tokens
            union = q_tokens | e_tokens
            jaccard = len(intersection) / len(union) if union else 0.0
            if jaccard > best_score:
                best_score = jaccard
                best_match = existing

        is_dup = best_score > 0.55  # 55% token overlap threshold
        return {
            "is_duplicate": is_dup,
            "similar_question": best_match if is_dup else None,
            "similarity": round(best_score, 2),
        }

    async def validate(
        self,
        question: str,
        category: str,
        difficulty: str,
        existing_questions: Optional[List[str]] = None,
    ) -> dict:
        """
        Run all validation steps and emit an overall verdict.
        Steps run sequentially to avoid Groq rate limits on the free tier.
        """
        logger.info(f"Validating question: {question[:60]}...")

        answerability = await self.check_answerability(question, category, difficulty)
        difficulty_check = await self.check_difficulty_accuracy(question, category, difficulty)
        quality = await self.check_quality(question, category, difficulty)
        duplicate = await self.check_duplicate(question, existing_questions)

        # Overall verdict
        approved = (
            answerability["pass"]
            and not duplicate["is_duplicate"]
            and quality["quality_score"] >= 5.0
        )

        rejection_reasons = []
        if not answerability["pass"]:
            rejection_reasons.append(f"Not answerable: {answerability['reason']}")
        if duplicate["is_duplicate"]:
            rejection_reasons.append(f"Duplicate detected (similarity={duplicate['similarity']})")
        if quality["quality_score"] < 5.0:
            rejection_reasons.append(f"Quality too low ({quality['quality_score']:.1f}/10)")

        # Build suggested edit — prefer the quality check's edit over the answerability rewrite
        suggested_edit = quality.get("suggested_edit") or answerability.get("suggested_rewrite")

        logger.info(
            f"Validation verdict: {'approved' if approved else 'rejected'}, "
            f"quality={quality['quality_score']:.1f}"
        )

        return {
            "approved": approved,
            "rejection_reasons": rejection_reasons,
            "quality_score": quality["quality_score"],
            "quality_strengths": quality["strengths"],
            "quality_weaknesses": quality["weaknesses"],
            "suggested_edit": suggested_edit,
            "suggested_difficulty": difficulty_check["suggested_difficulty"],
            "difficulty_accurate": difficulty_check["accurate"],
            "difficulty_reason": difficulty_check["reason"],
            "is_duplicate": duplicate["is_duplicate"],
            "similar_question": duplicate["similar_question"],
            "answerability": answerability,
        }


validator_agent = ValidatorAgent()
