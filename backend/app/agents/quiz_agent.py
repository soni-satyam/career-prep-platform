"""Practice Quizzes Agent: multiple-choice quizzes in several question styles."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from app.agents.llm_utils import run_json_agent

MIN_QUESTIONS = 3
MAX_QUESTIONS = 20


@dataclass(frozen=True)
class QuestionType:
    id: str
    label: str
    description: str          # shown in the UI
    guide: str                # instructions added to the prompt
    tokens_per_question: int  # rough output size, used for per-minute token budgets


QUESTION_TYPES: dict[str, QuestionType] = {
    t.id: t
    for t in [
        QuestionType(
            "mixed",
            "Mix-up",
            "A blend of concepts, real-world scenarios, code reading and tricky questions.",
            "Mix several kinds of question so the quiz feels varied. Follow the exact mix given below.",
            280,
        ),
        QuestionType(
            "interview",
            "Interview style",
            "Questions interviewers actually ask: why, when, and trade-offs.",
            "Write questions the way a real interviewer would ask them in a technical round: probe understanding "
            "('why', 'when would you', 'what happens if', trade-offs), not trivia. Wrong options must be common "
            "misconceptions a half-prepared candidate would pick. The explanation should read like the answer a "
            "strong candidate would give, including the trade-off. Use categories such as Concept, Trade-off, Scenario.",
            300,
        ),
        QuestionType(
            "assessment",
            "Assessment style",
            "Online-test / screening-round style: crisp, timed, one clear answer.",
            "Write questions in the style of an online assessment or screening test: short (about 60 words or fewer), "
            "unambiguous, exactly one defensible answer, answerable in about a minute. Mix fundamentals, output "
            "prediction and short problem solving; no opinion questions. Order the set from easier to harder. "
            "Use categories such as Fundamentals, Output prediction, Problem solving, Debugging.",
            220,
        ),
        QuestionType(
            "most_asked",
            "Most asked",
            "Classic, high-frequency questions on the topic.",
            "Write the classic questions about this topic that come up again and again in interviews and exams. "
            "Start with the most frequently asked subtopics, cover at least as many distinct subtopics as you can "
            "(up to 6), and avoid obscure edge cases or trivia. Set each category to the subtopic the question "
            "belongs to (for example 'Joins', 'Indexes'). This reflects commonly asked patterns from general "
            "knowledge, not live interview data.",
            250,
        ),
        QuestionType(
            "conceptual",
            "Conceptual",
            "Fundamentals and how things work under the hood.",
            "Focus on fundamentals: definitions that matter, how and why things work, and the differences between "
            "closely related ideas. No code-reading questions. Set each category to the subtopic.",
            250,
        ),
        QuestionType(
            "practical",
            "Practical / scenario",
            "Real-world situations, debugging and design choices.",
            "Focus on applied, real-world questions: short situations where the learner must choose an approach, "
            "diagnose a problem, or apply a best practice. Use categories such as Scenario, Debugging, Best practice, "
            "Design choice.",
            300,
        ),
        QuestionType(
            "coding",
            "Code & output",
            "Read code, predict output, spot bugs.",
            "Every question must include a short code snippet (12 lines or fewer) in a fenced block and ask for the "
            "output, the bug, the complexity, or the missing line. If the topic is not a programming language or "
            "tool, use the closest equivalent artifact instead (a query, a command, a config, a formula or "
            "pseudocode). Use categories such as Output prediction, Bug spotting, Complexity, Completion.",
            350,
        ),
    ]
}
QUESTION_TYPE_IDS = tuple(QUESTION_TYPES)

SYSTEM_TEMPLATE = """You are an expert technical interviewer writing practice quizzes.
Generate multiple-choice questions. Return ONLY valid JSON, no markdown outside the JSON.

Schema:
{{
  "topic": "string",
  "difficulty": "easy | medium | hard",
  "questions": [
    {{
      "id": "q1",
      "category": "short label such as Concept, Scenario, Code, or a subtopic name",
      "question": "clear question text",
      "options": ["first option text", "second option text", "third option text", "fourth option text"],
      "correct_index": 0,
      "explanation": "why the answer is correct"
    }}
  ]
}}

Rules:
- Return exactly the requested number of questions, no fewer.
- Exactly 4 options per question, with exactly one correct answer. Do not prefix options with letters or numbers.
- correct_index is 0-based. Spread the correct answer across all four positions; do not always use the same one.
- Wrong options must be plausible, not obviously silly.
- Questions must not repeat or overlap; cover different aspects of the topic.
- If a question needs code, put it inside the question string in a fenced block (```), using \\n for line breaks.
- Match the requested difficulty: easy = fundamentals, medium = working knowledge, hard = depth and edge cases.

Question style: {label}
{guide}
{mix}"""

_MIX_RATIOS = (("Concept", 0.30), ("Scenario", 0.30), ("Code", 0.25), ("Tricky", 0.15))


def mix_plan(n: int) -> dict[str, int]:
    """How many of each kind a Mix-up quiz of n questions contains (sums to n, each >= 1 when n >= 4)."""
    counts = {k: int(math.floor(n * r)) for k, r in _MIX_RATIOS}
    if n >= len(_MIX_RATIOS):
        counts = {k: max(1, v) for k, v in counts.items()}
    # hand out / take back leftovers in ratio order so the total is exactly n
    order = [k for k, _ in _MIX_RATIOS]
    i = 0
    while sum(counts.values()) < n:
        counts[order[i % len(order)]] += 1
        i += 1
    i = len(order) - 1
    while sum(counts.values()) > n:
        k = order[i % len(order)]
        if counts[k] > 1 or n < len(order):
            counts[k] -= 1
        i -= 1
    return counts


def resolve_type(question_type: str) -> QuestionType:
    return QUESTION_TYPES.get(question_type) or QUESTION_TYPES["mixed"]


def build_system_prompt(question_type: str, num_questions: int) -> str:
    qt = resolve_type(question_type)
    mix = ""
    if qt.id == "mixed":
        plan = mix_plan(num_questions)
        parts = ", ".join(f"{v} {k}" for k, v in plan.items() if v)
        mix = (
            f"Use exactly this mix: {parts}. Set each question's category to its kind "
            "(Concept, Scenario, Code or Tricky) and interleave the kinds rather than grouping them. "
            "'Code' questions include a short snippet; 'Tricky' questions test a common gotcha or misconception. "
            "If the topic is not a programming topic, replace Code questions with applied Scenario questions."
        )
    return SYSTEM_TEMPLATE.format(label=qt.label, guide=qt.guide, mix=mix).rstrip() + "\n"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def min_acceptable(wanted: int) -> int:
    """Fewer than this many valid questions makes the router try another provider."""
    return min(wanted, max(MIN_QUESTIONS, math.ceil(0.6 * wanted)))


def _make_validator(topic: str, difficulty: str, question_type: str, wanted: int):
    """Strict check so a malformed quiz fails over to another provider instead of
    reaching the UI as an empty list (which made users click again)."""
    qt = resolve_type(question_type)
    min_ok = min_acceptable(wanted)

    def validate(data: dict[str, Any]) -> dict[str, Any]:
        good: list[dict[str, Any]] = []
        seen: set[str] = set()
        for q in data.get("questions") or []:
            if not isinstance(q, dict):
                continue
            options = q.get("options")
            idx = q.get("correct_index")
            text = q.get("question")
            if not (
                isinstance(text, str)
                and text.strip()
                and isinstance(options, list)
                and len(options) == 4
                and all(isinstance(o, str) and o.strip() for o in options)
                and isinstance(idx, int)
                and not isinstance(idx, bool)
                and 0 <= idx < 4
            ):
                continue
            key = _norm(text)
            if key in seen:
                continue
            seen.add(key)
            category = q.get("category")
            good.append(
                {
                    "id": f"q{len(good) + 1}",
                    "category": category.strip()[:40] if isinstance(category, str) and category.strip() else "",
                    "question": text.strip(),
                    "options": [o.strip() for o in options],
                    "correct_index": idx,
                    "explanation": str(q.get("explanation") or ""),
                }
            )
        if len(good) < min_ok:
            raise ValueError(f"only {len(good)} valid quiz questions (need {min_ok})")
        return {
            "topic": str(data.get("topic") or topic),
            "difficulty": difficulty,
            "question_type": qt.id,
            "num_requested": wanted,
            "questions": good[:wanted],
        }

    return validate


async def generate_quiz(
    topic: str,
    difficulty: str = "medium",
    num_questions: int = 5,
    context: str = "",
    question_type: str = "mixed",
) -> dict[str, Any]:
    num_questions = max(MIN_QUESTIONS, min(MAX_QUESTIONS, int(num_questions)))
    qt = resolve_type(question_type)
    user = f"""Topic: {topic}
Difficulty: {difficulty}
Question style: {qt.label}
Number of questions: {num_questions}
Extra context (JD / skills, optional):
{context[:4000] if context else "(none)"}
"""
    # No result cache: "New quiz" must give new questions. dedupe only merges
    # identical requests that are running at the same moment (double click).
    return await run_json_agent(
        build_system_prompt(qt.id, num_questions),
        user,
        temperature=0.4,
        dedupe=True,
        validator=_make_validator(topic, difficulty, qt.id, num_questions),
        est_output_tokens=300 + qt.tokens_per_question * num_questions,
    )
