"""Resume Tailoring / Generation Agent — adapted from AI Career Copilot."""

from __future__ import annotations

from typing import Any

from app.agents.contracts import TailoredResume
from app.agents.llm_utils import run_json_agent

SYSTEM = """You are an expert resume writer for tech roles.
Given a job description analysis and a candidate profile, produce a tailored resume.
Return ONLY a valid JSON object, no markdown.

Schema:
{
  "profile": {
    "name": "", "email": "", "phone": "", "city": "", "school": "", "github": ""
  },
  "summary": "2-3 sentence targeted summary",
  "skills": ["ordered by relevance to the JD"],
  "experience": [
    {"id": "exp_1", "title": "Role @ Company", "content": "STAR-style bullets as one string", "source_refs": []}
  ],
  "projects": [
    {"id": "proj_1", "title": "Project name", "content": "STAR-style description", "source_refs": []}
  ],
  "education": [
    {"id": "edu_1", "school": "", "major": "", "degree": "", "start_date": "", "end_date": ""}
  ],
  "awards": [
    {"id": "award_1", "title": "", "content": "", "source_refs": []}
  ]
}

Rules:
- NEVER invent experience, projects, or metrics the candidate did not provide
- Reorder and rephrase to highlight JD-relevant skills
- Use STAR format for experience and projects
- Skills ordered by importance to the target role
"""


async def generate_tailored_resume(
    jd_analysis: dict,
    profile: dict,
    edit_instruction: str = "",
) -> dict[str, Any]:
    extra = f"\nAdditional edit instruction from user:\n{edit_instruction}" if edit_instruction else ""
    user = f"""Job analysis:
{jd_analysis}

Candidate profile:
{profile}
{extra}
"""
    return await run_json_agent(SYSTEM, user, schema=TailoredResume, temperature=0.3, est_output_tokens=3500)
