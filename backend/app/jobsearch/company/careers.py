"""Read a company's own career page and return its jobs.

Strategy, cheapest and most reliable first:
  1. schema.org `JobPosting` JSON-LD on the listing page (what Google for Jobs reads);
  2. job lists embedded as JSON (Next.js `__NEXT_DATA__` and similar);
  3. groups of links that look like individual postings, followed to their detail pages for JSON-LD;
  4. an embedded Greenhouse / Lever / Ashby / ... board, reported so the caller can use that board's API.

Pages that render their listing only in the browser (JavaScript single-page apps) cannot be read this way;
that is reported as `js_rendered` rather than pretending there are no jobs.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.jobsearch.company.discover import (
    AtsBoard, ListedJob, PageInfo, board_from_url, detect_boards, extract_embedded_jobs, extract_job_links,
    next_page_url, parse_page,
)
from app.jobsearch.company.identify import same_site
from app.jobsearch.company.net import safe_get, text_of
from app.jobsearch.posting import JobPosting
from app.jobsearch.sources.base import SourceContext, parse_dt
from app.jobsearch.sources.career_page import parse_job_postings
from app.jobsearch.text import infer_seniority

logger = logging.getLogger("careerprep.jobs")

_BLOCK_MARKERS = re.compile(r"captcha|are you a robot|access denied|attention required|verify you are human|just a moment", re.I)
_REMOTE_HINT = re.compile(r"\bremote\b|\bhybrid\b|\bon-?site\b", re.I)


@dataclass
class CareerReport:
    url: str
    status: str = "unreachable"     # ok | boards_only | js_rendered | blocked | empty | unreachable
    jobs_found: int = 0
    note: str = ""
    boards: list[AtsBoard] = field(default_factory=list)


def _location_from(extras: list[str]) -> str:
    for line in extras:
        for bit in re.split(r"\s[·|•–—-]\s", line):
            if _REMOTE_HINT.search(bit):
                return bit.strip()
    for line in extras:
        for bit in re.split(r"\s[·|•–—-]\s", line):
            if "," in bit and len(bit) <= 60:
                return bit.strip()
    return ""


def _from_listing(item: ListedJob) -> JobPosting:
    loc = _location_from(item.extras)
    return JobPosting(
        title=item.title, company="", url=item.url, source="career_page", location=loc,
        description=" · ".join(item.extras), seniority=infer_seniority(item.title), external_id=item.url,
    )


def _from_embedded(e: dict) -> JobPosting:
    et = e.get("employment_type", "").lower().replace("_", "-").replace(" ", "-")
    return JobPosting(
        title=e["title"], company="", url=e["url"], source="career_page", location=e.get("location", ""),
        posted_at=parse_dt(e.get("posted")), description=e.get("department", ""),
        employment_type={"fulltime": "full-time", "parttime": "part-time"}.get(et, et),
        seniority=infer_seniority(e["title"]), external_id=e["url"],
    )


async def _fetch_page(ctx: SourceContext, url: str) -> tuple[int, str] | None:
    r = await safe_get(ctx.client, url, headers={"Accept": "text/html,application/xhtml+xml"})
    if r is None:
        return None
    return r.status_code, text_of(r)


async def _detail(ctx: SourceContext, item: ListedJob, sem: asyncio.Semaphore) -> Optional[JobPosting]:
    """A job's own page: prefer its JSON-LD, else fall back to what the listing link told us."""
    async with sem:
        try:
            got = await _fetch_page(ctx, item.url)
        except Exception as exc:  # noqa: BLE001 - one bad page must not hide the rest
            logger.info("job page skipped: %s", type(exc).__name__)
            got = None
    if got and got[0] < 400 and got[1]:
        jobs = parse_job_postings(got[1], item.url)
        if jobs:
            j = jobs[0]
            j.url = j.url or item.url
            return j
    return _from_listing(item)


def _looks_js_rendered(page: PageInfo) -> bool:
    return len(page.text) < 600 and len(page.srcs) >= 1


async def scrape_career_page(ctx: SourceContext, url: str, *, max_pages: int = 3, max_detail: int = 25) -> tuple[list[JobPosting], CareerReport]:
    key = f"careerscrape:{url}"
    cached = ctx.cache.get(key)
    if cached is not None:
        return cached

    report = CareerReport(url=url)
    pages: list[tuple[str, PageInfo, str]] = []
    visited: set[str] = set()
    cur = url
    for i in range(max_pages):
        visited.add(cur)
        try:
            got = await _fetch_page(ctx, cur)
        except Exception as exc:  # noqa: BLE001
            logger.info("career page %s unreachable: %s", cur, type(exc).__name__)
            got = None
        if got is None:
            if i == 0:
                report.status, report.note = "unreachable", "The career page could not be reached from our servers."
            break
        status, html = got
        if status in (401, 403, 429) or (status < 400 and _BLOCK_MARKERS.search(html[:4000] or "") and len(html) < 20000):
            if i == 0:
                report.status, report.note = "blocked", "The company's site blocks automated access to this page."
            break
        if status >= 400:
            if i == 0:
                report.status, report.note = "unreachable", f"The career page returned HTTP {status}."
            break
        page = parse_page(html)
        pages.append((cur, page, html))
        nxt = next_page_url(page, cur)
        if not nxt or nxt in visited or not same_site(nxt, url):
            break
        cur = nxt

    if not pages:
        out = ([], report)
        ctx.cache.set(key, out, min(ctx.cache_ttl, 120))
        return out

    report.boards = detect_boards(*[h for _, _, h in pages])
    found: dict[str, JobPosting] = {}

    def add(j: JobPosting) -> None:
        k = j.url if j.url and j.url not in {p[0] for p in pages} else f"{j.url}|{j.title}"
        found.setdefault(k, j)

    to_follow: list[ListedJob] = []
    for purl, page, html in pages:
        for j in parse_job_postings(html, purl):
            add(j)
        for e in extract_embedded_jobs(page, purl):
            add(_from_embedded(e))
        to_follow.extend(extract_job_links(page, purl))

    # job links not already covered by JSON-LD / embedded data. Links to an ATS board are skipped:
    # that board's API returns the same jobs with better data.
    todo = [l for l in to_follow if l.url not in found and not board_from_url(l.url)]
    sem = asyncio.Semaphore(8)
    detailed = await asyncio.gather(*[_detail(ctx, l, sem) for l in todo[:max_detail]])
    for j in detailed:
        if j:
            add(j)
    for l in todo[max_detail:]:
        add(_from_listing(l))

    jobs = list(found.values())
    report.jobs_found = len(jobs)
    if jobs:
        report.status = "ok"
        report.note = f"Read {len(jobs)} job{'s' if len(jobs) != 1 else ''} directly from the career page."
    elif report.boards:
        names = ", ".join(sorted({b.provider.title() for b in report.boards}))
        report.status = "boards_only"
        report.note = f"This career page is powered by {names}; jobs are read from there."
    elif any(_looks_js_rendered(p) for _, p, _ in pages):
        report.status = "js_rendered"
        report.note = ("This career page loads its job list with JavaScript, so it can't be read automatically. "
                       "Open it directly, or use the results from other sources below.")
    else:
        report.status = "empty"
        report.note = "No job listings were found on the career page. There may be no open roles right now."

    out = (jobs, report)
    ctx.cache.set(key, out, ctx.cache_ttl)
    return out
