"""Gap Analysis Agent — adapted from AI Career Copilot."""

from __future__ import annotations

from typing import Any

from app.agents.contracts import GapAnalysis
from app.agents.llm_utils import run_json_agent
from app.core.config import get_settings

SYSTEM = """You are an expert career gap analyst for tech candidates.
Compare the job requirements against the candidate profile and identify gaps and strengths.
Return ONLY a valid JSON object, no markdown.

Schema:
{
  "overall_readiness": "ready | almost | needs_work | significant_gap",
  "gaps": [
    {
      "id": "gap_1",
      "type": "missing_skill | missing_experience | no_quantification | low_relevance",
      "severity": "high | medium | low",
      "description": "what is missing",
      "how_to_close": "concrete advice",
      "related_skills": ["..."]
    }
  ],
  "strengths": ["what the candidate already has that matches"],
  "questions_to_ask": ["clarifying questions to strengthen the profile"]
}

Be realistic and encouraging. Prefer concrete actions.
"""


async def analyze_gaps(jd_analysis: dict, profile: dict) -> dict[str, Any]:
    user = f"""Job analysis:
{jd_analysis}

Candidate profile:
{profile}
"""
    return await run_json_agent(
        SYSTEM, user, schema=GapAnalysis, cache_ttl=get_settings().llm_cache_ttl_seconds
    )
