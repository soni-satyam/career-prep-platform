"""Interview Q&A Agent — adapted from AI Career Copilot."""

from __future__ import annotations

from typing import Any

from app.agents.contracts import InterviewPack
from app.agents.llm_utils import run_json_agent

SYSTEM = """You are an expert interview coach for tech roles.
Generate defensive interview Q&A based on the job, candidate profile, and (optional) tailored resume.
Return ONLY a valid JSON object, no markdown.

Schema:
{
  "interview_qa": [
    {
      "id": "qa_1",
      "category": "technical | project_deep_dive | behavioral | system_design",
      "question": "the interview question",
      "answer": "strong sample answer grounded in the candidate's materials",
      "tips": "short tip for delivering the answer"
    }
  ],
  "focus_areas": ["topics the candidate should practice most"]
}

Rules:
- Generate at least 8 questions covering technical, project deep-dive, and behavioral
- Answers must be grounded in provided materials — do not invent experience
- Include a mix of difficulty levels
"""


async def generate_interview_pack(
    jd_analysis: dict,
    profile: dict,
    tailored_resume: dict | None = None,
    num_questions: int = 8,
) -> dict[str, Any]:
    resume_part = f"\nTailored resume:\n{tailored_resume}" if tailored_resume else ""
    user = f"""Job analysis:
{jd_analysis}

Candidate profile:
{profile}
{resume_part}

Generate about {num_questions} high-quality interview Q&As.
"""
    return await run_json_agent(SYSTEM, user, schema=InterviewPack, temperature=0.4, est_output_tokens=4000)
