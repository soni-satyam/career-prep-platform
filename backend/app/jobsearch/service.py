"""Orchestrates one search across every configured source."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from app.core.config import Settings, get_settings
from app.jobsearch.matching import CandidateProfileView, MatchResult, score_job
from app.jobsearch.posting import JobPosting, SearchFilters, source_label
from app.jobsearch.ranking import dedupe, passes_filters, sort_jobs
from app.jobsearch.sources.aggregators import AdzunaSource, JoobleSource, JSearchSource, RemotiveSource
from app.jobsearch.sources.ats import AshbySource, GreenhouseSource, LeverSource
from app.jobsearch.sources.base import JobSource, SourceContext, SourceNotConfigured, TTLCache
from app.jobsearch.sources.career_page import CareerPageSource

logger = logging.getLogger("careerprep.jobs")

_cache = TTLCache()
_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={"User-Agent": "CareerPrep/1.0 (+job-search; contact via app)", "Accept": "application/json"},
            follow_redirects=True,
        )
    return _client


def set_client(client: Optional[httpx.AsyncClient]) -> None:
    """For tests."""
    global _client
    _client = client


def reset_cache() -> None:
    _cache.clear()


def build_sources(s: Settings) -> list[JobSource]:
    return [
        CareerPageSource(s.job_career_page_urls),
        GreenhouseSource(s.job_greenhouse_boards),
        LeverSource(s.job_lever_companies),
        AshbySource(s.job_ashby_boards),
        JSearchSource(s.jsearch_api_key),
        AdzunaSource(s.adzuna_app_id, s.adzuna_app_key),
        JoobleSource(s.jooble_api_key),
        RemotiveSource(s.job_remotive_enabled),
    ]


@dataclass
class SourceStatus:
    name: str
    status: str                 # ok | skipped | error | filtered_out
    count: int = 0
    message: str = ""


@dataclass
class SearchResult:
    jobs: list[tuple[JobPosting, Optional[MatchResult]]]
    total: int
    page: int
    page_size: int
    sources: list[SourceStatus]
    facets: dict[str, int] = field(default_factory=dict)
    profile_used: bool = False


async def _run_source(src: JobSource, ctx: SourceContext, f: SearchFilters, timeout: float) -> tuple[JobSource, list[JobPosting] | Exception]:
    try:
        return src, await asyncio.wait_for(src.fetch(ctx, f), timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - isolate every source
        return src, exc


def _describe(exc: Exception) -> str:
    if isinstance(exc, asyncio.TimeoutError):
        return "timed out"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return f"rejected the API key (HTTP {code})"
        if code == 429:
            return "rate limit reached (HTTP 429), try again later"
        return f"HTTP {code}"
    return f"{type(exc).__name__}"


async def search_jobs(
    f: SearchFilters,
    profile: Optional[CandidateProfileView] = None,
    *,
    page: int = 1,
    page_size: int = 20,
    settings: Optional[Settings] = None,
    sources: Optional[list[JobSource]] = None,
) -> SearchResult:
    s = settings or get_settings()
    srcs = sources if sources is not None else build_sources(s)
    ctx = SourceContext(client=get_client(), cache=_cache, cache_ttl=float(s.job_cache_ttl_seconds),
                        default_country=s.job_default_country)
    if not f.country:
        f.country = s.job_default_country

    wanted = {x.lower() for x in f.sources}
    if "other" in wanted:
        wanted |= {"adzuna", "jooble", "remotive"}
    statuses: dict[str, SourceStatus] = {}
    active: list[JobSource] = []
    for src in srcs:
        if not src.configured():
            statuses[src.name] = SourceStatus(src.name, "skipped", message=src.not_configured_hint())
        else:
            active.append(src)

    started = time.monotonic()
    done = await asyncio.gather(*[_run_source(x, ctx, f, s.job_source_timeout_seconds) for x in active])

    collected: list[JobPosting] = []
    for src, res in done:
        if isinstance(res, Exception):
            msg = _describe(res)
            logger.warning("job source %s failed: %s", src.name, msg)
            statuses[src.name] = SourceStatus(src.name, "error", message=msg)
            continue
        kept = [j for j in res if j.title and j.url
                and passes_filters(j, f, search_locally=not src.server_side_search)]
        statuses[src.name] = SourceStatus(src.name, "ok", count=len(kept),
                                          message=f"{len(res)} fetched" if len(res) != len(kept) else "")
        collected.extend(kept)

    deduped = dedupe(collected)
    # the "sources" filter applies to where a job ended up, after dedupe keeps the best source
    if wanted:
        deduped = [j for j in deduped if j.source in wanted or any(a["source"] in wanted for a in j.also_on)]

    matches: dict[str, Optional[MatchResult]] = {}
    if profile is not None and profile.usable:
        for j in deduped:
            matches[j.uid] = score_job(j, profile)
    match_of = lambda j: (matches.get(j.uid).score if matches.get(j.uid) else -1)  # noqa: E731

    ordered = sort_jobs(deduped, f.sort, match_of, query=f.q)[: s.job_max_results]
    facets: dict[str, int] = {}
    for j in ordered:
        facets[j.source] = facets.get(j.source, 0) + 1

    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    window = ordered[(page - 1) * page_size: page * page_size]
    logger.info("job search q=%r loc=%r -> %d results from %d sources in %.1fs",
                f.q, f.location, len(ordered), len(active), time.monotonic() - started)
    return SearchResult(
        jobs=[(j, matches.get(j.uid)) for j in window],
        total=len(ordered), page=page, page_size=page_size,
        sources=list(statuses.values()), facets=facets,
        profile_used=bool(profile and profile.usable),
    )
