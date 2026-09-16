"""Full preparation pipeline orchestrator.

Runs: JD analysis → Profile extraction → Gap analysis →
      Tailored resume → Interview pack → Multi-week plan
"""

from __future__ import annotations

import asyncio
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


# Which optional steps each mode runs. JD analysis and profile extraction always run.
#   full      -> everything (default; what the API did before)
#   resume    -> the Resume page shows gaps, tailored resume and resume tips; it never
#                shows interview Q&A, so that call is skipped.
#   interview -> the Interview page shows only Q&A + focus areas, so gap analysis,
#                resume tailoring and the weekly plan are skipped.
PIPELINE_MODES: dict[str, frozenset[str]] = {
    "full": frozenset({"gap", "resume", "interview", "plan"}),
    "resume": frozenset({"gap", "resume", "plan"}),
    "interview": frozenset({"interview"}),
}


async def run_full_pipeline(
    jd_text: str,
    resume_text: str = "",
    target_role: str = "",
    company: str = "",
    mode: str = "full",
) -> dict[str, Any]:
    """Execute the multi-agent preparation pipeline."""
    steps = PIPELINE_MODES.get(mode, PIPELINE_MODES["full"])
    has_resume = bool(resume_text.strip())

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
            "mode": mode,
        },
    }

    # 1 + 2. JD analysis and profile extraction don't depend on each other.
    empty_profile = {
        "profile_basic": {},
        "facts": [],
        "skills": [],
        "summary": "",
    }
    if has_resume:
        result["jd_analysis"], result["profile"] = await asyncio.gather(
            analyze_jd(jd_text), extract_profile(resume_text)
        )
    else:
        result["jd_analysis"] = await analyze_jd(jd_text)
        result["profile"] = empty_profile

    jd, profile = result["jd_analysis"], result["profile"]

    # 3 + 4. Gap analysis and resume tailoring both only need (jd, profile).
    parallel = []
    if "gap" in steps:
        parallel.append(("gap_analysis", analyze_gaps(jd, profile)))
    if "resume" in steps and has_resume:
        parallel.append(("tailored_resume", generate_tailored_resume(jd, profile)))
    if parallel:
        outputs = await asyncio.gather(*(coro for _, coro in parallel))
        for (key, _), value in zip(parallel, outputs):
            result[key] = value

    # 5. Interview pack
    if "interview" in steps:
        result["interview_pack"] = await generate_interview_pack(
            jd, profile, result.get("tailored_resume")
        )

    # 6. Multi-week plan (+ resume tips)
    if "plan" in steps:
        plan_user = f"""JD analysis: {jd}
Profile: {profile}
Gap analysis: {result['gap_analysis']}
Target role: {target_role or jd.get('title', '')}
Company: {company}
"""
        plan_data = await run_json_agent(
            PLAN_SYSTEM, plan_user, temperature=0.3, est_output_tokens=2500
        )
        result["preparation_plan"] = plan_data.get("preparation_plan", [])
        result["estimated_weeks"] = plan_data.get("estimated_weeks", 4)
        result["resume_tips"] = plan_data.get("resume_tips", [])

    return result
