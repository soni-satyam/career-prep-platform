"""Preparation Plan Agent.

Takes a job description + candidate profile/resume text and produces:
- Structured JD analysis
- Gap analysis (skills / experience)
- A concrete multi-week preparation plan
- Suggested interview focus areas
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.agents.llm_utils import run_json_agent


class SkillGap(BaseModel):
    skill: str
    importance: str = Field(description="high | medium | low")
    current_level: str = Field(description="none | beginner | intermediate | advanced")
    target_level: str
    how_to_close: str


class WeekPlan(BaseModel):
    week: int
    focus: str
    tasks: list[str]
    resources: list[str] = []


class PreparationPlan(BaseModel):
    role_summary: str
    key_requirements: list[str]
    must_have_skills: list[str]
    nice_to_have_skills: list[str]
    gap_analysis: list[SkillGap]
    overall_readiness: str = Field(description="ready | almost | needs_work | significant_gap")
    preparation_plan: list[WeekPlan]
    interview_focus: list[str]
    resume_tips: list[str]
    estimated_weeks: int


SYSTEM_PROMPT = """You are an expert career coach and technical recruiter specializing in tech roles.
You help candidates land specific jobs by creating realistic, actionable preparation plans.

Always respond with valid JSON that matches this schema:
{
  "role_summary": "1-2 sentence summary of the role",
  "key_requirements": ["..."],
  "must_have_skills": ["..."],
  "nice_to_have_skills": ["..."],
  "gap_analysis": [
    {
      "skill": "...",
      "importance": "high|medium|low",
      "current_level": "none|beginner|intermediate|advanced",
      "target_level": "...",
      "how_to_close": "concrete advice"
    }
  ],
  "overall_readiness": "ready|almost|needs_work|significant_gap",
  "preparation_plan": [
    {
      "week": 1,
      "focus": "...",
      "tasks": ["..."],
      "resources": ["..."]
    }
  ],
  "interview_focus": ["topics / question types to practice"],
  "resume_tips": ["specific changes to make the resume stronger for this JD"],
  "estimated_weeks": 4
}

Be realistic and encouraging. Prefer concrete actions over vague advice.
If the candidate is already strong, say so and focus on interview polish.
"""


async def generate_preparation_plan(
    jd_text: str,
    resume_text: str = "",
    target_role: str = "",
    company: str = "",
) -> dict[str, Any]:
    """Generate a full preparation plan from JD + optional resume."""

    user_content = f"""Target Role: {target_role or "Not specified"}
Company: {company or "Not specified"}

=== JOB DESCRIPTION ===
{jd_text.strip()[:12000]}

=== CANDIDATE RESUME / PROFILE ===
{resume_text.strip()[:8000] if resume_text else "(No resume provided — analyze JD only and give general preparation advice)"}

Create a detailed preparation plan to maximize the chance of landing this role.
"""
    return await run_json_agent(SYSTEM_PROMPT, user_content, temperature=0.2)
