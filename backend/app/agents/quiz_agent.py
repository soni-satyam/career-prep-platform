"""Practice Quizzes Agent: multiple-choice quizzes in several question styles."""

from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Optional

from app.agents.llm_utils import run_json_agent

logger = logging.getLogger("careerprep.quiz")

MIN_QUESTIONS = 3
MAX_QUESTIONS = 20
# Models reliably follow a count of ~10 but drift on longer lists, so bigger quizzes are written
# as parallel batches of at most this many questions.
MAX_BATCH = 10
# If the total is still short, ask for the missing ones (telling the model what already exists).
MAX_TOPUP_ROUNDS = 2


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
- The "questions" array must contain exactly {count} items: no fewer, no more. Count them before answering.
- Exactly 4 options per question, with exactly one correct answer. Do not prefix options with letters or numbers.
- correct_index is 0-based. Spread the correct answer across all four positions; do not always use the same one.
- Wrong options must be plausible, not obviously silly.
- Questions must not repeat or overlap; cover different aspects of the topic.
- If a question needs code, put it inside the question string in a fenced block (```), using \\n for line breaks.
- Match the requested difficulty: easy = fundamentals, medium = working knowledge, hard = depth and edge cases.

Question style: {label}
{guide}
{mix}{part}"""

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


def _part_note(part: Optional[tuple[int, int, int]], question_type: str) -> str:
    """For a batch of a larger quiz: keep parts distinct and shape the difficulty/coverage curve."""
    if not part or part[1] <= 1:
        return ""
    index, count, total = part
    first, last = index == 0, index == count - 1
    if question_type == "assessment":
        focus = "This part is the easier half of the quiz." if first else "This part is the harder half of the quiz."
    elif first:
        focus = "Prioritise the most fundamental and most commonly tested aspects of the topic."
    elif last:
        focus = "Prioritise deeper, more applied or less obvious aspects; avoid the first things that come to mind."
    else:
        focus = "Prioritise intermediate aspects between the fundamentals and the advanced details."
    return (
        f"\nThis is part {index + 1} of {count} of a {total}-question quiz. The other parts are written "
        f"separately, so keep your questions distinct from the obvious ones. {focus}"
    )


def build_system_prompt(
    question_type: str, num_questions: int, part: Optional[tuple[int, int, int]] = None
) -> str:
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
    return (
        SYSTEM_TEMPLATE.format(
            label=qt.label, guide=qt.guide, mix=mix, count=num_questions, part=_part_note(part, qt.id)
        ).rstrip()
        + "\n"
    )


def build_user_message(
    topic: str,
    difficulty: str,
    qt: QuestionType,
    size: int,
    context: str = "",
    exclude: Optional[list[str]] = None,
) -> str:
    msg = f"""Topic: {topic}
Difficulty: {difficulty}
Question style: {qt.label}
Number of questions: {size} (the "questions" array must contain exactly {size} items)
Extra context (JD / skills, optional):
{context[:4000] if context else "(none)"}
"""
    if exclude:
        listed = "\n".join(f"- {q.strip().splitlines()[0][:110]}" for q in exclude[:30])
        msg += (
            "\nThese questions already exist in the quiz. Do NOT repeat or closely paraphrase them, "
            f"and cover different aspects:\n{listed}\n"
        )
    return msg


def plan_batches(n: int) -> list[int]:
    """Split n questions into near-equal batches of at most MAX_BATCH (15 -> [8, 7], 20 -> [10, 10])."""
    parts = max(1, math.ceil(n / MAX_BATCH))
    base, extra = divmod(n, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


_Sig = tuple[str, frozenset[str], frozenset[str]]  # (normalised question, question tokens, correct-answer tokens)


def _tokens(text: str) -> frozenset[str]:
    # keep digits and short tokens: for code/aptitude questions they are the whole difference
    return frozenset(_norm(text).split())


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def _signature(q: dict[str, Any]) -> _Sig:
    return _norm(q["question"]), _tokens(q["question"]), _tokens(q["options"][q["correct_index"]])


def _is_duplicate(sig: _Sig, seen: list[_Sig]) -> bool:
    """Same question twice (typically from two parallel batches). Two questions that read alike but
    have different answers ('what does x = 5 print' vs 'x = 6') are NOT duplicates."""
    norm, words, correct = sig
    for other_norm, other_words, other_correct in seen:
        if norm == other_norm:
            return True
        if _jaccard(words, other_words) >= 0.85 and _jaccard(correct, other_correct) >= 0.5:
            return True
    return False


def _clean_question(q: Any) -> Optional[dict[str, Any]]:
    if not isinstance(q, dict):
        return None
    options, idx, text = q.get("options"), q.get("correct_index"), q.get("question")
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
        return None
    category = q.get("category")
    return {
        "category": category.strip()[:40] if isinstance(category, str) and category.strip() else "",
        "question": text.strip(),
        "options": [o.strip() for o in options],
        "correct_index": idx,
        "explanation": str(q.get("explanation") or ""),
    }


def _merge(into: list[dict[str, Any]], seen: list[_Sig], new: list[dict[str, Any]]) -> int:
    """Append questions that are not duplicates of what we already have. Returns how many were added."""
    added = 0
    for q in new:
        sig = _signature(q)
        if _is_duplicate(sig, seen):
            continue
        seen.append(sig)
        into.append(q)
        added += 1
    return added


def _make_validator(size: int):
    """A batch needs at least one well-formed question, otherwise the router tries another provider.
    Being short is NOT a failure here: generate_quiz tops the quiz up itself, which is cheaper and more
    reliable than asking a different model for the whole batch again."""

    def validate(data: dict[str, Any]) -> dict[str, Any]:
        good = [c for c in (_clean_question(q) for q in (data.get("questions") or [])) if c]
        if not good:
            raise ValueError("no valid quiz questions")
        return {"topic": data.get("topic"), "questions": good[:size]}

    return validate


async def _run_batch(
    topic: str,
    difficulty: str,
    qt: QuestionType,
    size: int,
    context: str,
    part: Optional[tuple[int, int, int]] = None,
    exclude: Optional[list[str]] = None,
) -> dict[str, Any]:
    # No result cache: "New quiz" must give new questions. dedupe only merges identical
    # requests that are running at the same moment (double click).
    return await run_json_agent(
        build_system_prompt(qt.id, size, part),
        build_user_message(topic, difficulty, qt, size, context, exclude),
        temperature=0.4,
        dedupe=True,
        validator=_make_validator(size),
        est_output_tokens=300 + qt.tokens_per_question * size,
    )


async def generate_quiz(
    topic: str,
    difficulty: str = "medium",
    num_questions: int = 5,
    context: str = "",
    question_type: str = "mixed",
) -> dict[str, Any]:
    """Return exactly `num_questions` questions whenever the providers can supply them.

    1. Split into parallel batches of <= MAX_BATCH (one call for up to 10 questions).
    2. De-duplicate across batches.
    3. If still short, up to MAX_TOPUP_ROUNDS "top-up" calls ask only for the missing questions,
       listing the existing ones so they are not repeated.
    The response reports `num_requested` so the UI can say so honestly if a provider fell short.
    """
    n = max(MIN_QUESTIONS, min(MAX_QUESTIONS, int(num_questions)))
    qt = resolve_type(question_type)
    sizes = plan_batches(n)

    outcomes = await asyncio.gather(
        *(
            _run_batch(topic, difficulty, qt, size, context, (i, len(sizes), n) if len(sizes) > 1 else None)
            for i, size in enumerate(sizes)
        ),
        return_exceptions=True,
    )
    questions: list[dict[str, Any]] = []
    seen: list[_Sig] = []
    first_error: Optional[BaseException] = None
    resolved_topic = None
    for out in outcomes:
        if isinstance(out, BaseException):
            first_error = first_error or out
            continue
        resolved_topic = resolved_topic or out.get("topic")
        _merge(questions, seen, out["questions"])
    if not questions and first_error is not None:
        raise first_error

    rounds = 0
    while len(questions) < n and rounds < MAX_TOPUP_ROUNDS:
        rounds += 1
        missing = min(n - len(questions), MAX_BATCH)
        try:
            more = await _run_batch(
                topic, difficulty, qt, missing, context, exclude=[q["question"] for q in questions]
            )
        except Exception as exc:  # noqa: BLE001 - a failed top-up must not discard a good quiz
            logger.info("quiz top-up failed (%s); returning %d of %d", type(exc).__name__, len(questions), n)
            break
        _merge(questions, seen, more["questions"])

    questions = questions[:n]
    for i, q in enumerate(questions, 1):
        q["id"] = f"q{i}"
    logger.info(
        "quiz generated: style=%s requested=%d batches=%s topup_rounds=%d returned=%d",
        qt.id, n, sizes, rounds, len(questions),
    )
    return {
        "topic": str(resolved_topic or topic),
        "difficulty": difficulty,
        "question_type": qt.id,
        "num_requested": n,
        "questions": questions,
    }
