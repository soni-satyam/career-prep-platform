"""Filtering, de-duplication and ordering of normalised postings."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from app.jobsearch.posting import JobPosting, SearchFilters, source_label
from app.jobsearch.relevance import ParsedQuery, parse_query, score_title
from app.jobsearch.text import location_matches

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

# ---------------------------------------------------------------- inferred fields
# Greenhouse/aggregators rarely fill employment_type / work_mode, so "unknown passes every
# filter" made the Work mode and Job type filters look broken. Fill the gaps from the posting
# text; only genuinely unknowable cases fall through (see passes_filters).

_HYBRID_RE = re.compile(r"\bhybrid\b", re.I)
_ONSITE_RE = re.compile(r"\bon[\s-]?site\b|\bin[\s-]office\b|\bwork from office\b|\bwfo\b", re.I)
_REMOTE_TITLE_LOC_RE = re.compile(r"\bremote\b|\bwork from home\b|\bwfh\b|\banywhere\b", re.I)
_REMOTE_DESC_RE = re.compile(
    r"\b(fully|100%|completely)[\s-]remote\b|\bremote[\s-]first\b|\bwork from (home|anywhere)\b"
    r"|\bremote (position|role|job|opportunity)\b|\bthis (role|position|job) is remote\b", re.I)
_TYPE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("internship", re.compile(r"\bintern(ship)?s?\b|\btrainee\b", re.I)),
    ("part-time", re.compile(r"\bpart[\s-]?time\b", re.I)),
    ("contract", re.compile(r"\bcontract(or)?\b|\bfreelance\b|\bfixed[\s-]term\b|\bconsultant\b", re.I)),
    ("full-time", re.compile(r"\bfull[\s-]?time\b|\bpermanent\b", re.I)),
]


def effective_work_mode(job: JobPosting) -> str:
    """remote | hybrid | onsite | '' (unknown). Uses the source's value first, then the text."""
    if job.work_mode in ("remote", "hybrid", "onsite"):
        return job.work_mode
    if job.remote:
        return "remote"
    head = f"{job.title} {job.location}"
    body = (job.description or "")[:2500]
    if _HYBRID_RE.search(head) or _HYBRID_RE.search(body):
        return "hybrid"
    if _REMOTE_TITLE_LOC_RE.search(head) or _REMOTE_DESC_RE.search(body):
        return "remote"
    if _ONSITE_RE.search(head) or _ONSITE_RE.search(body):
        return "onsite"
    # a posting tied to a real city with no remote/hybrid wording is, in practice, on-site
    return "onsite" if (job.location or "").strip() else ""


def effective_employment_type(job: JobPosting) -> str:
    """full-time | part-time | contract | internship. Postings with no signal are treated as
    full-time (the overwhelming default); title wins over description."""
    if job.employment_type:
        return _norm_type(job.employment_type)
    for text in (job.title or "", (job.description or "")[:2500]):
        for kind, pat in _TYPE_PATTERNS:
            if pat.search(text):
                return kind
    return "full-time"


def passes_filters(job: JobPosting, f: SearchFilters, *, search_locally: bool, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)

    # Title relevance is enforced for EVERY source. Aggregators match q loosely server-side (they
    # happily return "Software Engineer" for "AI Engineer" because the description mentions AI),
    # so trusting them is what let unrelated roles through.
    if f.q and score_title(f.q, job.title, job.description) is None:
        return False

    if f.company and f.company.lower() not in (job.company or "").lower():
        return False

    # work mode / location
    mode = effective_work_mode(job)
    if f.work_mode == "remote":
        if mode != "remote":
            return False
    else:
        if f.work_mode and mode != f.work_mode:
            return False
        if f.location and not location_matches(job.location, f.location):
            if not (mode == "remote" and not f.work_mode):      # remote jobs stay unless the user asked for on-site/hybrid
                return False

    if f.employment_type and effective_employment_type(job) != f.employment_type:
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


def sort_jobs(jobs: list[JobPosting], mode: str, match_of: Callable[[JobPosting], int] | None = None,
              query: str | ParsedQuery = "") -> list[JobPosting]:
    ts = lambda j: (j.posted_at or _EPOCH).timestamp()  # noqa: E731
    pq = query if isinstance(query, ParsedQuery) else parse_query(query)
    rel: dict[int, tuple[int, int]] = {}
    if not pq.empty:
        for j in jobs:
            r = score_title(pq, j.title, j.description)
            rel[id(j)] = (r.tier, -r.score) if r else (99, 0)
    rk = lambda j: rel.get(id(j), (0, 0))  # noqa: E731
    if mode == "recent":
        return sorted(jobs, key=lambda j: (-ts(j), j.priority))
    if mode == "match" and match_of is not None:
        return sorted(jobs, key=lambda j: (-match_of(j), rk(j), j.priority, -ts(j)))
    # priority: the closer the TITLE is to what was searched, the higher it ranks; then
    # career page > greenhouse > lever > ... > other; newest first inside each source tier.
    # With no query every job has the same relevance, so this is the old ordering.
    return sorted(jobs, key=lambda j: (rk(j), j.priority, -ts(j)))
