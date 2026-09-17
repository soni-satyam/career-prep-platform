"""Fill in the filterable fields a source did not provide, from the title / location / description.

Why: aggregators (Adzuna, Jooble, JSearch ...) often return no work mode, job type or experience. The
filters used to treat "unknown" as "passes", so choosing On-site / Internship / Contract / 0-2 yrs hid
almost nothing and the list looked unchanged. Inferring the value makes the filter bite on real data.
"""

from __future__ import annotations

import re

from app.jobsearch.posting import JobPosting
from app.jobsearch.text import infer_seniority, parse_experience, years_from_seniority

_REMOTE = re.compile(r"\b(remote|work from home|wfh|work from anywhere|fully distributed|telecommut\w*)\b", re.I)
_HYBRID = re.compile(r"\bhybrid\b|\b\d\s*days?\s+(?:a|per)\s+week\s+(?:in|at)\s+(?:the\s+)?office\b", re.I)
_ONSITE = re.compile(r"\b(on[\s-]?site|onsite|in[\s-]office|work from office|wfo|office[\s-]based)\b", re.I)

_TYPE_RULES: list[tuple[str, re.Pattern]] = [
    ("internship", re.compile(r"\b(intern|internship|trainee|apprentice(?:ship)?)\b", re.I)),
    ("contract", re.compile(r"\b(contract(?:or)?|freelance|fixed[\s-]term|c2h|contract[\s-]to[\s-]hire|consultant\s+basis)\b", re.I)),
    ("part-time", re.compile(r"\bpart[\s-]?time\b", re.I)),
    ("full-time", re.compile(r"\bfull[\s-]?time\b|\bpermanent\b", re.I)),
]


def infer_work_mode(job: JobPosting) -> str:
    if job.work_mode in ("remote", "hybrid", "onsite"):
        return job.work_mode
    head = f"{job.title}. {job.location}"
    body = (job.description or "")[:3000]
    if _HYBRID.search(head) or _HYBRID.search(body):
        return "hybrid"
    if _REMOTE.search(head) or job.remote:
        return "remote"
    if _ONSITE.search(head) or _ONSITE.search(body):
        return "onsite"
    if _REMOTE.search(body[:600]):          # "remote" only near the top counts; later it is usually boilerplate
        return "remote"
    # A concrete place and no remote/hybrid signal anywhere -> a physical office job.
    return "onsite" if (job.location or "").strip() else ""


def infer_employment_type(job: JobPosting) -> str:
    if job.employment_type:
        return job.employment_type
    head = f"{job.title}. {job.location}"
    body = (job.description or "")[:3000]
    for kind, rx in _TYPE_RULES:
        if rx.search(head):
            return kind
    for kind, rx in _TYPE_RULES:
        if rx.search(body):
            return kind
    return ""


def enrich(job: JobPosting) -> JobPosting:
    """Mutates and returns `job`. Never overwrites a value the source gave us."""
    mode = infer_work_mode(job)
    if mode and not job.work_mode:
        job.work_mode = mode
        job.remote = job.remote or mode == "remote"

    et = infer_employment_type(job)
    if et and not job.employment_type:
        job.employment_type = et

    if job.experience_min is None and job.experience_max is None:
        lo, hi = parse_experience(f"{job.title}. {job.description}")
        if lo is None and hi is None:
            lo, hi = years_from_seniority(job.seniority or infer_seniority(job.title))
        job.experience_min, job.experience_max = lo, hi
    return job
