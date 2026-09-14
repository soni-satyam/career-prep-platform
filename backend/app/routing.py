"""PART 5a - Conditional edges: small functions that decide "where next?".

A router reads the state and returns the NAME of the next node(s).
"""
from langgraph.graph import END

from app import config
from app.state import EvalState, PrepState


def route_after_validation(state: PrepState):
    """Bad input -> stop immediately. Good input -> fan out to two nodes in parallel."""
    if not state.get("is_valid"):
        return END
    return ["analyst", "company_researcher"]


def route_after_review(state: PrepState) -> str:
    """Approved (or out of retries) -> build report. Otherwise loop back to the generator."""
    review = state["review"]
    if review.approved or state.get("attempts", 0) > config.MAX_REGENERATIONS:
        return "report_builder"
    return "question_generator"


def route_eval_start(state: EvalState) -> str:
    """Don't spend LLM calls on an empty / throwaway answer."""
    if len(state.get("user_answer", "").strip()) < 20:
        return "reject_answer"
    return "answer_evaluator"
