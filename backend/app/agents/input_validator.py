"""PART 4a - Node 1: Input validator (NO LLM - pure code, so it is free and instant).

Cleans text, rejects unusable input early (saves LLM calls), warns on suspicious input.
"""
from app import config
from app.state import PrepState
from app.tools.text_utils import clean_text, looks_like_job_description, looks_like_resume


def input_validator_node(state: PrepState) -> dict:
    resume = clean_text(state.get("resume_text", ""))
    jd = clean_text(state.get("job_description", ""))
    company = (state.get("company_name") or "").strip()

    problems = []
    if len(resume) < config.MIN_RESUME_CHARS:
        problems.append("Resume is too short or unreadable (scanned PDFs need OCR).")
    if len(jd) < config.MIN_JD_CHARS:
        problems.append("Job description is too short.")
    if not company:
        problems.append("Company name is missing.")
    if problems:
        return {"is_valid": False, "validation_error": " ".join(problems)}

    warnings = []
    if not looks_like_resume(resume):
        warnings.append("Resume has no recognisable sections (experience/education/skills).")
    if not looks_like_job_description(jd):
        warnings.append("Job description doesn't look like a typical JD; results may be generic.")

    return {
        "resume_text": resume,
        "job_description": jd,
        "company_name": company,
        "is_valid": True,
        "attempts": 0,
        "errors": warnings,
    }
