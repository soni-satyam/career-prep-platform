"""PART 2a - The *shape* of what each agent must return.

Passed to llm.with_structured_output(), so the LLM answers in clean JSON.
(We avoid min/max constraints in the schemas - some free providers reject
them - and clamp numbers in code instead.)
"""
from typing import Literal
from pydantic import BaseModel, Field


# ---------- Agent 1: analyst ----------
class ResumeJDAnalysis(BaseModel):
    candidate_summary: str = Field(description="2-3 sentence summary of the candidate")
    seniority_level: str = Field(description="e.g. intern, junior, mid, senior")
    matched_skills: list[str] = Field(description="Skills in both resume and JD")
    skill_gaps: list[str] = Field(description="JD requirements missing from the resume")
    key_requirements: list[str] = Field(description="Top requirements of the role")
    focus_areas: list[str] = Field(description="Topics the candidate should prepare most")


# ---------- Agent 2: company researcher ----------
class CompanyInsights(BaseModel):
    overview: str = Field(description="What the company does")
    products_services: list[str] = Field(default_factory=list)
    culture_values: list[str] = Field(default_factory=list)
    recent_news: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    interview_style: str = Field(description="Known interview process, or 'unknown'")
    sources: list[str] = Field(default_factory=list, description="Leave empty; filled by code")


# ---------- Agent 3: study planner ----------
class StudyItem(BaseModel):
    topic: str
    priority: Literal["high", "medium", "low"]
    why: str = Field(description="Why this matters for THIS job")
    estimated_hours: int
    free_resources: list[str] = Field(
        description="Names of free resources/sites (e.g. 'MDN', 'freeCodeCamp'). NO URLs."
    )
    practice_task: str = Field(description="One concrete exercise to do")


class StudyPlan(BaseModel):
    summary: str
    items: list[StudyItem]


# ---------- Agent 4: question generator ----------
class Question(BaseModel):
    category: Literal["technical", "behavioral", "company_specific", "gap_based", "role_specific"]
    question: str
    why_asked: str = Field(description="What the interviewer is testing")
    answer_hint: str = Field(description="Short outline of a strong answer using the candidate's background")


class QuestionSet(BaseModel):
    questions: list[Question]


# ---------- Agent 5: quality reviewer ----------
class ReviewVerdict(BaseModel):
    """What the LLM judge returns."""
    specificity_score: int = Field(description="1-10. 10 = every question is tailored to this candidate/company/job")
    issues: list[str] = Field(default_factory=list, description="Concrete problems, e.g. 'Q3 is generic'")


class ReviewResult(BaseModel):
    """What our reviewer node stores in state."""
    approved: bool
    issues: list[str] = Field(default_factory=list)
    specificity_score: int | None = None


# ---------- Mock-interview graph ----------
class AnswerFeedback(BaseModel):
    score: int = Field(description="1-10")
    strengths: list[str]
    improvements: list[str]
    uses_star_structure: bool = Field(description="Situation/Task/Action/Result clearly present?")
    improved_answer_outline: str


class FollowUp(BaseModel):
    follow_up_question: str
    reason: str = Field(description="Why a real interviewer would ask this next")
