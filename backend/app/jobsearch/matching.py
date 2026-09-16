"""Profile match %.

score = weighted average of the parts we can actually evaluate for this job:

  skills      60%  share of the skills the job mentions that the candidate has
  title       25%  overlap between the candidate's role/title and the job title
  experience  15%  candidate years vs. the job's required range

A part that cannot be evaluated (job lists no recognisable skills, candidate years unknown, ...)
is left out and the remaining weights are re-normalised, so a missing field never counts as 0%.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.jobsearch.posting import JobPosting
from app.jobsearch.text import canonical_skill, extract_skills, infer_seniority, title_tokens, years_from_seniority

W_SKILLS, W_TITLE, W_EXP = 0.60, 0.25, 0.15
_GENERIC = {"engineer", "senior", "junior", "lead", "staff", "principal", "manager", "ii", "iii", "i", "associate"}


@dataclass
class CandidateProfileView:
    skills: list[str] = field(default_factory=list)
    title: str = ""
    experience_years: Optional[float] = None

    def __post_init__(self) -> None:
        self.skills = [canonical_skill(s) for s in self.skills if s and s.strip()]
        self._skill_set = {s.lower() for s in self.skills}

    @property
    def usable(self) -> bool:
        return bool(self._skill_set or self.title or self.experience_years is not None)

    def has(self, skill: str) -> bool:
        return skill.lower() in self._skill_set


@dataclass
class MatchResult:
    score: int
    matched_skills: list[str]
    missing_skills: list[str]
    parts: dict[str, Optional[float]]


def _experience_fit(years: float, lo: Optional[float], hi: Optional[float]) -> Optional[float]:
    if lo is None and hi is None:
        return None
    lo = lo if lo is not None else 0.0
    if years < lo:
        gap = lo - years
        return max(0.0, 1.0 - gap / max(lo, 1.0))
    if hi is not None and years > hi + 3:
        return max(0.5, 1.0 - (years - hi - 3) * 0.1)     # over-qualified: mild penalty only
    return 1.0


def score_job(job: JobPosting, profile: CandidateProfileView) -> Optional[MatchResult]:
    if not profile.usable:
        return None

    job_skills = extract_skills(f"{job.title}\n{job.description}")
    matched = [s for s in job_skills if profile.has(s)]
    missing = [s for s in job_skills if not profile.has(s)]

    skill_part: Optional[float] = None
    if job_skills and profile.skills:
        skill_part = len(matched) / len(job_skills)

    title_part: Optional[float] = None
    if profile.title:
        pt, jt = set(title_tokens(profile.title)), set(title_tokens(job.title))
        pt_core, jt_core = pt - _GENERIC, jt - _GENERIC
        if jt:
            if pt_core and jt_core:
                title_part = len(pt_core & jt_core) / len(jt_core)
            else:
                title_part = len(pt & jt) / len(jt)
            if not (pt_core & jt_core) and (pt & jt):
                title_part = max(title_part, 0.4)        # both "engineer" but different domains

    exp_part: Optional[float] = None
    if profile.experience_years is not None:
        lo, hi = job.experience_min, job.experience_max
        if lo is None and hi is None:
            lo, hi = years_from_seniority(job.seniority or infer_seniority(job.title))
        exp_part = _experience_fit(profile.experience_years, lo, hi)

    parts = {"skills": skill_part, "title": title_part, "experience": exp_part}
    weights = {"skills": W_SKILLS, "title": W_TITLE, "experience": W_EXP}
    used = {k: v for k, v in parts.items() if v is not None}
    if not used:
        return None
    total_w = sum(weights[k] for k in used)
    score = sum(weights[k] * v for k, v in used.items()) / total_w
    return MatchResult(
        score=int(round(score * 100)),
        matched_skills=matched[:12],
        missing_skills=missing[:8],
        parts=parts,
    )
