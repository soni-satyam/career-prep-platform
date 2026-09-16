"""Profile Extraction Agent — adapted from AI Career Copilot."""

from __future__ import annotations

from typing import Any

from app.agents.contracts import ProfileExtraction
from app.agents.llm_utils import run_json_agent
from app.core.config import get_settings

SYSTEM = """You are an expert at building candidate profiles from resumes and free-form text.
Extract structured information. Return ONLY a valid JSON object, no markdown.

Schema:
{
  "profile_basic": {
    "name": "", "email": "", "phone": "", "city": "", "school": "", "github": ""
  },
  "facts": [
    {
      "id": "fact_skill_1",
      "type": "skill | project | internship | award | paper | experience",
      "content": "detailed structured description",
      "source_refs": ["resume"]
    }
  ],
  "skills": ["Python", "React", "..."],
  "summary": "2-3 sentence professional summary"
}

Rules:
- Do NOT invent facts not present in the material
- For projects/experience include: name, role, tech, impact when available
- skills list should be a flat list of skill names
"""


async def extract_profile(resume_text: str, existing: dict | None = None) -> dict[str, Any]:
    existing_str = str(existing) if existing else "(none)"
    user = f"""Candidate material:
{resume_text.strip()[:12000]}

Existing profile (merge, do not overwrite known fields with empty):
{existing_str}
"""
    return await run_json_agent(
        SYSTEM, user, schema=ProfileExtraction,
        cache_ttl=get_settings().llm_cache_ttl_seconds,
        est_output_tokens=2000,
    
    )
