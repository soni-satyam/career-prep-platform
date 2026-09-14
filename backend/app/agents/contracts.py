"""Pydantic contracts for agent structured outputs (adapted from AI Career Copilot)."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class JDAnalysis(BaseModel):
    industry: str = ""
    title: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    hard_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    education_requirement: str = ""
    experience_requirement: str = ""
    implicit_preferences: list[str] = Field(default_factory=list)
    bonus_items: list[str] = Field(default_factory=list)


class ProfileBasic(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""
    school: str = ""
    github: str = ""


class ProfileFact(BaseModel):
    id: str = ""
    type: str = "skill"  # skill | project | internship | award | paper | experience
    content: str = ""
    source_refs: list[str] = Field(default_factory=list)


class ProfileExtraction(BaseModel):
    profile_basic: ProfileBasic = Field(default_factory=ProfileBasic)
    facts: list[ProfileFact] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    summary: str = ""


class GapItem(BaseModel):
    id: str = ""
    type: str = "missing_skill"  # missing_skill | missing_experience | no_quantification | low_relevance
    severity: str = "medium"  # high | medium | low
    description: str = ""
    how_to_close: str = ""
    related_skills: list[str] = Field(default_factory=list)


class GapAnalysis(BaseModel):
    overall_readiness: str = "needs_work"  # ready | almost | needs_work | significant_gap
    gaps: list[GapItem] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(default_factory=list)


class EducationItem(BaseModel):
    id: str = ""
    school: str = ""
    major: str = ""
    degree: str = ""
    start_date: str = ""
    end_date: str = ""


class ResumeSection(BaseModel):
    id: str = ""
    title: str = ""
    content: str = ""
    source_refs: list[str] = Field(default_factory=list)


class TailoredResume(BaseModel):
    profile: ProfileBasic = Field(default_factory=ProfileBasic)
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[ResumeSection] = Field(default_factory=list)
    projects: list[ResumeSection] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    awards: list[ResumeSection] = Field(default_factory=list)


class InterviewQA(BaseModel):
    id: str = ""
    category: str = "technical"  # technical | project_deep_dive | behavioral | system_design
    question: str = ""
    answer: str = ""
    tips: str = ""


class InterviewPack(BaseModel):
    interview_qa: list[InterviewQA] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)


class WeekPlan(BaseModel):
    week: int
    focus: str
    tasks: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)


class FullPrepResult(BaseModel):
    jd_analysis: Optional[JDAnalysis] = None
    profile: Optional[ProfileExtraction] = None
    gap_analysis: Optional[GapAnalysis] = None
    tailored_resume: Optional[TailoredResume] = None
    interview_pack: Optional[InterviewPack] = None
    preparation_plan: list[WeekPlan] = Field(default_factory=list)
    estimated_weeks: int = 4
    resume_tips: list[str] = Field(default_factory=list)
