"""Full preparation pipeline orchestrator.

Runs: JD analysis → Profile extraction → Gap analysis →
      Tailored resume → Interview pack → Multi-week plan
"""

from __future__ import annotations

from typing import Any, Optional

from app.agents.gap_agent import analyze_gaps
from app.agents.interview_agent import generate_interview_pack
from app.agents.jd_agent import analyze_jd
from app.agents.llm_utils import run_json_agent
from app.agents.profile_agent import extract_profile
from app.agents.resume_agent import generate_tailored_resume

PLAN_SYSTEM = """You are an expert career coach.
Given JD analysis, profile, and gap analysis, produce a realistic multi-week preparation plan.
Return ONLY valid JSON:

{
  "preparation_plan": [
    {"week": 1, "focus": "...", "tasks": ["..."], "resources": ["..."]}
  ],
  "estimated_weeks": 4,
  "resume_tips": ["specific tips to improve the resume for this JD"]
}
"""


async def run_full_pipeline(
    jd_text: str,
    resume_text: str = "",
    target_role: str = "",
    company: str = "",
) -> dict[str, Any]:
    """Execute the full multi-agent preparation pipeline."""

    result: dict[str, Any] = {
        "jd_analysis": None,
        "profile": None,
        "gap_analysis": None,
        "tailored_resume": None,
        "interview_pack": None,
        "preparation_plan": [],
        "estimated_weeks": 4,
        "resume_tips": [],
        "meta": {
            "target_role": target_role,
            "company": company,
        },
    }

    # 1. JD Analysis
    result["jd_analysis"] = await analyze_jd(jd_text)

    # 2. Profile Extraction
    if resume_text.strip():
        result["profile"] = await extract_profile(resume_text)
    else:
        result["profile"] = {
            "profile_basic": {},
            "facts": [],
            "skills": [],
            "summary": "",
        }

    # 3. Gap Analysis
    result["gap_analysis"] = await analyze_gaps(
        result["jd_analysis"], result["profile"]
    )

    # 4. Tailored Resume (only if we have profile material)
    if resume_text.strip():
        result["tailored_resume"] = await generate_tailored_resume(
            result["jd_analysis"], result["profile"]
        )

    # 5. Interview Pack
    result["interview_pack"] = await generate_interview_pack(
        result["jd_analysis"],
        result["profile"],
        result.get("tailored_resume"),
    )

    # 6. Multi-week plan
    plan_user = f"""JD analysis: {result['jd_analysis']}
Profile: {result['profile']}
Gap analysis: {result['gap_analysis']}
Target role: {target_role or result['jd_analysis'].get('title', '')}
Company: {company}
"""
    plan_data = await run_json_agent(PLAN_SYSTEM, plan_user, temperature=0.3)
    result["preparation_plan"] = plan_data.get("preparation_plan", [])
    result["estimated_weeks"] = plan_data.get("estimated_weeks", 4)
    result["resume_tips"] = plan_data.get("resume_tips", [])

    return result
