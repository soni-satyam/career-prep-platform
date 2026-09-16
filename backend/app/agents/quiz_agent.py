"""Practice Quizzes Agent."""

from __future__ import annotations

from typing import Any

from app.agents.llm_utils import run_json_agent

SYSTEM = """You are an expert technical interviewer writing practice quizzes.
Generate multiple-choice questions. Return ONLY valid JSON, no markdown.

Schema:
{
  "topic": "string",
  "difficulty": "easy | medium | hard",
  "questions": [
    {
      "id": "q1",
      "question": "clear question text",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0,
      "explanation": "why the answer is correct"
    }
  ]
}

Rules:
- Exactly 4 options per question
- correct_index is 0-based
- Prefer practical tech interview style
- Match the requested difficulty and topic
"""


def _make_validator(difficulty: str, wanted: int):
    """Strict check so a malformed quiz fails over to another provider
    instead of reaching the UI as an empty list (which made users click again)."""
    min_ok = max(1, min(wanted, 3))

    def validate(data: dict[str, Any]) -> dict[str, Any]:
        good = []
        for i, q in enumerate(data.get("questions") or []):
            if not isinstance(q, dict):
                continue
            options = q.get("options")
            idx = q.get("correct_index")
            if (
                isinstance(q.get("question"), str)
                and q["question"].strip()
                and isinstance(options, list)
                and len(options) == 4
                and all(isinstance(o, str) and o.strip() for o in options)
                and isinstance(idx, int)
                and not isinstance(idx, bool)
                and 0 <= idx < 4
            ):
                good.append(
                    {
                        "id": str(q.get("id") or f"q{len(good) + 1}"),
                        "question": q["question"].strip(),
                        "options": [o.strip() for o in options],
                        "correct_index": idx,
                        "explanation": str(q.get("explanation") or ""),
                    }
                )
        if len(good) < min_ok:
            raise ValueError(f"only {len(good)} valid quiz questions")
        data["questions"] = good[:wanted]
        data.setdefault("difficulty", difficulty)
        return data

    return validate


async def generate_quiz(
    topic: str,
    difficulty: str = "medium",
    num_questions: int = 5,
    context: str = "",
) -> dict[str, Any]:
    user = f"""Topic: {topic}
Difficulty: {difficulty}
Number of questions: {num_questions}
Extra context (JD / skills, optional):
{context[:4000] if context else "(none)"}
"""
    # No result cache: "New quiz" must give new questions. dedupe only merges
    # identical requests that are running at the same moment (double click).
    return await run_json_agent(
        SYSTEM,
        user,
        temperature=0.4,
        dedupe=True,
        validator=_make_validator(difficulty, num_questions),
        est_output_tokens=300 + 250 * num_questions,
    )
