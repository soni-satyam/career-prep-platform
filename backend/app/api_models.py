"""PART 7b - Request/response models. FastAPI turns these into the OpenAPI schema,
which your future TypeScript app can turn into types (e.g. `npx openapi-typescript`)."""
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import (
    AnswerFeedback, CompanyInsights, FollowUp, Question, ResumeJDAnalysis, ReviewResult, StudyPlan,
)

SessionStatus = Literal["pending", "running", "completed", "failed", "rejected"]


class QuestionOut(Question):
    id: str = Field(description="Stable id like 'technical-1'; used by the practice endpoint")


class FinalReport(BaseModel):
    markdown: str
    analysis: ResumeJDAnalysis
    company_insights: CompanyInsights
    study_plan: StudyPlan
    questions_by_category: dict[str, list[QuestionOut]]
    review: ReviewResult
    warnings: list[str]


class SessionCreated(BaseModel):
    session_id: str
    status: SessionStatus


class SessionOut(BaseModel):
    id: str
    status: SessionStatus
    company_name: str
    created_at: str
    error: str | None = None
    report: FinalReport | None = None


class PracticeRequest(BaseModel):
    question_id: str
    answer: str = Field(max_length=5000)
    follow_up_question: str | None = Field(
        default=None, max_length=1000,
        description="Set this to answer the interviewer's follow-up instead of the original question",
    )


class PracticeResult(BaseModel):
    attempt_id: int
    question_id: str
    question: str
    answer: str
    feedback: AnswerFeedback
    follow_up: FollowUp
    created_at: str


class GraphInfo(BaseModel):
    nodes: list[str]
    edges: list[tuple[str, str, bool]] = Field(description="(source, target, is_conditional)")


class Health(BaseModel):
    status: str
    llm_provider: str
    llm_configured: bool
