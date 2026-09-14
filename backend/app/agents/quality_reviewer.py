"""PART 4f - Node 6: Quality Reviewer. This makes the graph truly *agentic*.

Step 1: cheap deterministic checks (counts, duplicates, empty fields).
Step 2: only if those pass, an LLM judge scores how tailored the questions are.
The router (routing.py) then decides: approve -> report, or loop back to the generator.
"""
from collections import Counter

from langchain_core.messages import HumanMessage, SystemMessage

from app import config
from app.llm import get_llm
from app.schemas import Question, ReviewResult, ReviewVerdict
from app.state import PrepState

JUDGE_SYSTEM = (
    "You are a strict interview-prep reviewer. Score 1-10 how tailored these questions are "
    "to the candidate, company and role. Generic questions that could be asked of anyone "
    "should lower the score. List concrete issues."
)


def deterministic_checks(questions: list[Question]) -> list[str]:
    issues = []
    counts = Counter(q.category for q in questions)
    for cat, minimum in config.MIN_PER_CATEGORY.items():
        if counts.get(cat, 0) < minimum:
            issues.append(f"Need at least {minimum} '{cat}' questions, got {counts.get(cat, 0)}.")

    seen, dupes = set(), 0
    for q in questions:
        key = " ".join(q.question.lower().split())
        dupes += key in seen
        seen.add(key)
    if dupes:
        issues.append(f"{dupes} duplicate question(s).")

    thin = [q.question[:40] for q in questions if len(q.answer_hint) < 20 or len(q.why_asked) < 10]
    if thin:
        issues.append(f"Missing why_asked/answer_hint on: {thin[:3]}")
    return issues


def quality_reviewer_node(state: PrepState) -> dict:
    attempts = state.get("attempts", 0) + 1
    questions = state["questions"].questions
    issues = deterministic_checks(questions)
    score, errors = None, []

    if not issues and config.USE_LLM_REVIEW:
        try:
            compact = "\n".join(f"[{q.category}] {q.question}" for q in questions)
            llm = get_llm(temperature=0).with_structured_output(ReviewVerdict)
            verdict = llm.invoke([
                SystemMessage(content=JUDGE_SYSTEM),
                HumanMessage(content=(
                    f"Candidate: {state['analysis'].candidate_summary}\n"
                    f"Company: {state['company_name']}\n"
                    f"Key requirements: {state['analysis'].key_requirements}\n\n"
                    f"QUESTIONS:\n{compact}"
                )),
            ])
            score = max(1, min(int(verdict.specificity_score), 10))
            if score < config.MIN_SPECIFICITY_SCORE:
                issues += verdict.issues or ["Questions are too generic."]
        except Exception as e:                      # judge failure must not kill the run
            errors.append(f"LLM review skipped: {e}")

    result = ReviewResult(approved=not issues, issues=issues, specificity_score=score)
    return {
        "review": result,
        "review_feedback": "; ".join(issues),
        "attempts": attempts,
        "errors": errors,
    }
