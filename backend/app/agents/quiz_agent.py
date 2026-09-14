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
    return await run_json_agent(SYSTEM, user, temperature=0.4)
