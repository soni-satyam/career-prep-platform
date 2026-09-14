"""PART 2b - Shared LangGraph state for both graphs.

Think of it as a whiteboard every node can read from and write to.
Each node returns a dict; LangGraph merges it into this state.
"""
import operator
from typing import Annotated, TypedDict

from app.schemas import (
    AnswerFeedback, CompanyInsights, FollowUp, QuestionSet,
    ResumeJDAnalysis, ReviewResult, StudyPlan,
)


class PrepState(TypedDict, total=False):
    # ---- inputs ----
    resume_text: str
    job_description: str
    company_name: str
    # ---- written by input_validator ----
    is_valid: bool
    validation_error: str
    # ---- written by analyst ----
    keyword_overlap: dict          # deterministic skill match from tools/skills.py
    analysis: ResumeJDAnalysis
    # ---- written by company_researcher ----
    company_insights: CompanyInsights
    # ---- written by study_planner ----
    study_plan: StudyPlan
    # ---- question generation + review loop ----
    questions: QuestionSet
    review: ReviewResult
    review_feedback: str           # fed back to the generator on retry
    attempts: int                  # how many times the reviewer has run
    # ---- written by report_builder ----
    final_report: dict
    # Annotated + operator.add = "append, don't overwrite" (parallel nodes may both add).
    errors: Annotated[list[str], operator.add]


class EvalState(TypedDict, total=False):
    """State for the mock-interview graph (second graph)."""
    question: str
    user_answer: str
    resume_text: str
    company_name: str
    feedback: AnswerFeedback
    follow_up: FollowUp
    eval_error: str
