"""Live AI mock interview — question generation, answer evaluation, final report."""

from __future__ import annotations

from typing import Any, Optional

from app.agents.llm_utils import run_json_agent

START_SYSTEM = """You are an expert technical interviewer conducting a live mock interview.
Generate the FIRST interview question only. Return ONLY valid JSON, no markdown.

Schema:
{
  "question_id": "q1",
  "category": "technical | behavioral | system_design | project_deep_dive",
  "question": "the spoken question text (clear, conversational)",
  "hints_for_evaluator": "what a strong answer should cover"
}
"""

EVAL_SYSTEM = """You are an expert technical interviewer in a live mock interview.
Given the conversation so far and the candidate's latest answer, either:
- ask a relevant follow-up, OR
- move to the next distinct question.

Return ONLY valid JSON:
{
  "evaluation": {
    "score": 1-10,
    "feedback": "1-2 sentences of constructive feedback on the last answer",
    "strengths": ["..."],
    "improvements": ["..."]
  },
  "done": false,
  "next_question": {
    "question_id": "q2",
    "category": "technical | behavioral | system_design | project_deep_dive",
    "question": "next spoken question",
    "is_follow_up": true,
    "hints_for_evaluator": "..."
  }
}

If this should be the last question (time/quota reached), set "done": true and omit next_question
or set next_question to null.
Be fair, specific, and encouraging. Prefer one focused follow-up when the answer was thin.
"""

REPORT_SYSTEM = """You are an expert interview coach writing a final mock-interview report.
Return ONLY valid JSON:
{
  "overall_score": 1-10,
  "summary": "2-3 sentence overall assessment",
  "category_scores": {
    "technical": 1-10,
    "communication": 1-10,
    "problem_solving": 1-10,
    "behavioral": 1-10
  },
  "strengths": ["..."],
  "improvements": ["..."],
  "recommended_practice": ["concrete next steps"],
  "question_reviews": [
    {
      "question": "...",
      "score": 1-10,
      "note": "brief note"
    }
  ]
}
"""


async def start_interview(
    role: str,
    difficulty: str,
    duration_minutes: int,
    resume_context: str = "",
    jd_context: str = "",
) -> dict[str, Any]:
    user = f"""Role: {role}
Difficulty: {difficulty}
Interview duration target: ~{duration_minutes} minutes
Resume context: {resume_context[:3000] if resume_context else "(none)"}
JD context: {jd_context[:3000] if jd_context else "(none)"}

Ask a strong opening question for this interview.
"""
    return await run_json_agent(START_SYSTEM, user, temperature=0.5)


async def evaluate_and_continue(
    role: str,
    difficulty: str,
    history: list[dict[str, Any]],
    latest_answer: str,
    questions_asked: int,
    max_questions: int,
) -> dict[str, Any]:
    hist_lines = []
    for h in history[-12:]:
        hist_lines.append(f"Q ({h.get('category', '')}): {h.get('question', '')}")
        if h.get("answer"):
            hist_lines.append(f"A: {h.get('answer', '')}")
        if h.get("feedback"):
            hist_lines.append(f"Feedback: {h.get('feedback', '')}")

    force_done = questions_asked >= max_questions
    user = f"""Role: {role}
Difficulty: {difficulty}
Questions asked so far: {questions_asked}
Max questions: {max_questions}
Force end after this evaluation: {force_done}

Conversation:
{chr(10).join(hist_lines)}

Latest candidate answer:
{latest_answer}

Evaluate the latest answer. {"This must be the final turn — set done=true." if force_done else "Provide next_question or a follow-up."}
"""
    data = await run_json_agent(EVAL_SYSTEM, user, temperature=0.4)
    if force_done:
        data["done"] = True
        data["next_question"] = None
    return data


async def generate_final_report(
    role: str,
    difficulty: str,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    hist = []
    for h in history:
        hist.append(
            {
                "question": h.get("question"),
                "category": h.get("category"),
                "answer": h.get("answer"),
                "score": h.get("score"),
                "feedback": h.get("feedback"),
            }
        )
    user = f"""Role: {role}
Difficulty: {difficulty}
Full interview transcript (structured):
{hist}
"""
    return await run_json_agent(REPORT_SYSTEM, user, temperature=0.3)
