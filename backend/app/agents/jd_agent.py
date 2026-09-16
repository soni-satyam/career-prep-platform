"""JD Analysis Agent — adapted from AI Career Copilot."""

from __future__ import annotations

from typing import Any

from app.agents.contracts import JDAnalysis
from app.agents.llm_utils import run_json_agent
from app.core.config import get_settings

SYSTEM = """You are an expert job description analyst for tech roles.
Extract structured information from the JD. Return ONLY a valid JSON object, no markdown.

Schema:
{
  "industry": "string",
  "title": "string",
  "tech_stack": ["string"],
  "keywords": ["string"],
  "hard_skills": ["string"],
  "soft_skills": ["string"],
  "responsibilities": ["string"],
  "education_requirement": "string",
  "experience_requirement": "string",
  "implicit_preferences": ["string"],
  "bonus_items": ["string"]
}

Rules:
- Be specific on tech stack (include versions if mentioned)
- Implicit preferences = things implied but not stated directly
- Use empty string or [] when unknown
"""


async def analyze_jd(jd_text: str) -> dict[str, Any]:
    user = f"Job Description:\n\n{jd_text.strip()[:15000]}"
    return await run_json_agent(
        SYSTEM, user, schema=JDAnalysis, cache_ttl=get_settings().llm_cache_ttl_seconds
    )
