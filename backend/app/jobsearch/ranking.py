"""Filtering, de-duplication and ordering of normalised postings."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from app.jobsearch.posting import JobPosting, SearchFilters, source_label
from app.jobsearch.text import location_matches, query_matches_job

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _norm_type(t: str) -> str:
    t = (t or "").lower().replace("_", "-").replace(" ", "-")
    if "full" in t:
        return "full-time"
    if "part" in t:
        return "part-time"
    if "contract" in t or "freelance" in t:
        return "contract"
    if "intern" in t:
        return "internship"
    return t


def passes_filters(job: JobPosting, f: SearchFilters, *, search_locally: bool, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)

    if search_locally and f.q and not query_matches_job(f.q, job.title, job.description):
        return False

    if f.company and f.company.lower() not in (job.company or "").lower():
        return False

    # work mode / location
    if f.work_mode == "remote":
        if not (job.remote or job.work_mode == "remote"):
            return False
    else:
        if f.work_mode and job.work_mode and job.work_mode != f.work_mode:
            return False
        if f.location and not location_matches(job.location, f.location):
            if not (job.remote and not f.work_mode):      # remote jobs stay unless the user asked for on-site/hybrid
                return False

    if f.employment_type and job.employment_type and _norm_type(job.employment_type) != f.employment_type:
        return False

    if f.posted_within_days:
        if job.posted_at is None:
            return False
        if job.posted_at < now - timedelta(days=f.posted_within_days):
            return False

    # salary (annual). Only comparable when currencies agree.
    if f.salary_min:
        has_salary = (job.salary_max or job.salary_min) is not None
        comparable = has_salary and (not f.salary_currency or not job.salary_currency
                                     or job.salary_currency.upper() == f.salary_currency.upper())
        if comparable:
            top = job.salary_max if job.salary_max is not None else job.salary_min
            if top < f.salary_min:
                return False
        elif not f.include_unspecified_salary:
            return False

    # experience required by the job vs. the requested range (overlap test; unknown passes)
    if f.experience_min is not None or f.experience_max is not None:
        jlo, jhi = job.experience_min, job.experience_max
        if jlo is not None or jhi is not None:
            jlo = jlo if jlo is not None else 0.0
            jhi = jhi if jhi is not None else 99.0
            wlo = f.experience_min if f.experience_min is not None else 0.0
            whi = f.experience_max if f.experience_max is not None else 99.0
            if jhi < wlo or jlo > whi:
                return False
    return True


def dedupe(jobs: list[JobPosting]) -> list[JobPosting]:
    """Same company + title + city seen on several sources -> keep the best source, remember the rest."""
    best: dict[str, JobPosting] = {}
    for j in jobs:
        k = j.dedupe_key
        cur = best.get(k)
        if cur is None:
            best[k] = j
            continue
        keep, other = (j, cur) if _better(j, cur) else (cur, j)
        keep.also_on = _merge_also(keep, other)
        if keep.posted_at is None and other.posted_at is not None:
            keep.posted_at = other.posted_at
        if not keep.salary_min and other.salary_min:
            keep.salary_min, keep.salary_max, keep.salary_currency = other.salary_min, other.salary_max, other.salary_currency
        best[k] = keep
    return list(best.values())


def _better(a: JobPosting, b: JobPosting) -> bool:
    if a.priority != b.priority:
        return a.priority < b.priority
    return (a.posted_at or _EPOCH) > (b.posted_at or _EPOCH)


def _merge_also(keep: JobPosting, other: JobPosting) -> list[dict]:
    seen = {d["source"] for d in keep.also_on} | {keep.source}
    out = list(keep.also_on)
    for src, url in [(other.source, other.url)] + [(d["source"], d["url"]) for d in other.also_on]:
        if src not in seen:
            out.append({"source": src, "label": source_label(src), "url": url})
            seen.add(src)
    return out


def sort_jobs(jobs: list[JobPosting], mode: str, match_of: Callable[[JobPosting], int] | None = None) -> list[JobPosting]:
    ts = lambda j: (j.posted_at or _EPOCH).timestamp()  # noqa: E731
    if mode == "recent":
        return sorted(jobs, key=lambda j: (-ts(j), j.priority))
    if mode == "match" and match_of is not None:
        return sorted(jobs, key=lambda j: (-match_of(j), j.priority, -ts(j)))
    # priority: career page > greenhouse > lever > ... > other; newest first inside each tier
    return sorted(jobs, key=lambda j: (j.priority, -ts(j)))
