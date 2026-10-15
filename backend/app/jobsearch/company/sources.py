"""Job sources scoped to one company. Plug into `search_jobs(..., sources=[...])` so filters, sorting,
de-duplication and match % work exactly as on the main Jobs page."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
from typing import Callable, Optional

from app.jobsearch.company.careers import CareerReport, scrape_career_page
from app.jobsearch.company.discover import AtsBoard
from app.jobsearch.company.identify import (
    company_matches, name_tokens, registrable_label, same_site,
)
from app.jobsearch.posting import JobPosting, SearchFilters
from app.jobsearch.sources.ats import AshbySource, GreenhouseSource, LeverSource
from app.jobsearch.sources.ats_extra import RecruiteeSource, SmartRecruitersSource, WorkableSource
from app.jobsearch.sources.base import JobSource, SourceContext, SourceNotConfigured
from app.jobsearch.text import infer_seniority

logger = logging.getLogger("careerprep.jobs")

PROVIDERS = {
    "greenhouse": GreenhouseSource, "lever": LeverSource, "ashby": AshbySource,
    "workable": WorkableSource, "smartrecruiters": SmartRecruitersSource, "recruitee": RecruiteeSource,
}


class TrustedSource(JobSource):
    """A board we know belongs to the company: stamp the canonical company name on every job."""

    def __init__(self, inner: JobSource, company: str) -> None:
        self.inner, self.company = inner, company
        self.name, self.kind, self.server_side_search = inner.name, inner.kind, inner.server_side_search

    def configured(self) -> bool:
        return self.inner.configured()

    def not_configured_hint(self) -> str:
        return self.inner.not_configured_hint()

    async def fetch(self, ctx: SourceContext, f: SearchFilters) -> list[JobPosting]:
        return [dataclasses.replace(j, company=self.company, also_on=[]) for j in await self.inner.fetch(ctx, f)]


class ScopedSource(JobSource):
    """A general job API (JSearch, Adzuna, ...) narrowed to one company: search by company name and drop
    anything another company posted."""

    def __init__(self, inner: JobSource, company: str, aliases: list[str]) -> None:
        self.inner, self.company, self.aliases = inner, company, aliases
        self.name, self.kind, self.server_side_search = inner.name, inner.kind, inner.server_side_search

    def configured(self) -> bool:
        return self.inner.configured()

    def not_configured_hint(self) -> str:
        return self.inner.not_configured_hint()

    async def fetch(self, ctx: SourceContext, f: SearchFilters) -> list[JobPosting]:
        g = dataclasses.replace(f, q=f"{self.company} {f.q}".strip())
        jobs = await self.inner.fetch(ctx, g)
        return [dataclasses.replace(j, company=self.company, also_on=[]) for j in jobs
                if company_matches(j.company, self.company, self.aliases)]


class CareerScrapeSource(JobSource):
    name = "career_page"
    kind = "career_page"
    server_side_search = False

    def __init__(self, url: str, company: str, hint: str = "") -> None:
        self.url, self.company, self._hint = url, company, hint
        self.report: Optional[CareerReport] = None

    def configured(self) -> bool:
        return bool(self.url)

    def not_configured_hint(self) -> str:
        return self._hint or "No career page was found for this company."

    async def fetch(self, ctx: SourceContext, f: SearchFilters) -> list[JobPosting]:
        if not self.url:
            raise SourceNotConfigured(self.not_configured_hint())
        jobs, self.report = await scrape_career_page(ctx, self.url)
        return [dataclasses.replace(j, company=self.company, also_on=[]) for j in jobs]


def board_sources(boards: list[AtsBoard], company: str) -> list[JobSource]:
    slugs: dict[str, list[str]] = {}
    for b in boards:
        if b.provider in PROVIDERS and b.slug not in slugs.setdefault(b.provider, []):
            slugs[b.provider].append(b.slug)
    return [TrustedSource(PROVIDERS[p](s), company) for p, s in slugs.items()]


# --------------------------------------------------------------- guessed ATS boards (startups)

# Guessed slugs are only probed on providers whose listing includes the job text, because that text is the
# only trustworthy evidence the board belongs to this company (Lever / Ashby / ... derive the "company name"
# from the slug itself, so matching on it proves nothing).
PROBE_PROVIDERS = ("greenhouse", "lever", "ashby", "workable", "recruitee")


def validate_board(jobs: list[JobPosting], name: str, domain: str) -> bool:
    """A guessed slug is accepted only if the board's own job descriptions mention the company."""
    sample = jobs[:10]
    if not sample:
        return False
    toks = name_tokens(name)
    label = registrable_label(domain) if domain else ""
    hits = 0
    for j in sample:
        d = (j.description or "").lower()
        if (toks and all(t in d for t in toks)) or (len(label) >= 4 and label in d):
            hits += 1
    return hits >= min(2, len(sample))


async def probe_boards(ctx: SourceContext, name: str, domain: str, slugs: list[str],
                       hints: tuple[AtsBoard, ...] | list[AtsBoard] = ()) -> list[AtsBoard]:
    """Try the likely board slugs on every supported ATS (plus boards a search result named); keep the ones
    that exist and belong to the company."""
    async def one(provider: str, slug: str) -> Optional[AtsBoard]:
        try:
            jobs = await PROVIDERS[provider]([slug])._board(ctx, slug)    # noqa: SLF001 - cached download
        except Exception:  # noqa: BLE001 - 404 / timeout / odd payload: simply "not this board"
            return None
        return AtsBoard(provider, slug) if validate_board(jobs, name, domain) else None

    pairs = list(dict.fromkeys([(p, s) for p in PROBE_PROVIDERS for s in slugs]
                               + [(b.provider, b.slug) for b in hints if b.provider in PROBE_PROVIDERS]))
    res = await asyncio.gather(*[one(p, s) for p, s in pairs])
    return [b for b in res if b]


# --------------------------------------------------------------- web search

_PORTALS: list[tuple[str, re.Pattern]] = [
    ("linkedin", re.compile(r"linkedin\.com/jobs/view/", re.I)),
    ("naukri", re.compile(r"naukri\.com/job-listings-", re.I)),
    ("indeed", re.compile(r"indeed\.[a-z.]+/(?:viewjob|rc/clk|job/)", re.I)),
    ("glassdoor", re.compile(r"glassdoor\.[a-z.]+/job-listing/", re.I)),
    ("wellfound", re.compile(r"wellfound\.com/(?:jobs/|company/[^/]+/jobs/)", re.I)),
    ("instahyre", re.compile(r"instahyre\.com/job-", re.I)),
    ("yc", re.compile(r"(?:ycombinator\.com/companies/[^/]+/jobs/|workatastartup\.com/jobs/)", re.I)),
]
_SITE_SUFFIX = re.compile(
    r"\s*[|\-–—]\s*(?:LinkedIn|Naukri(?:\.com)?|Indeed(?:\.com)?|Glassdoor|Wellfound|AngelList(?: Talent)?|Instahyre|Y Combinator|Work at a Startup)\b.*$", re.I)
_LISTING_TITLE = re.compile(r"^(?:jobs?|careers?|job openings?|open positions?|current openings?|hiring)\b", re.I)


def parse_result_title(title: str, company: str) -> tuple[str, str]:
    """(role, location) from a search-result title such as 'Acme hiring Backend Engineer in Pune | LinkedIn'."""
    t = " ".join((title or "").split())
    m = re.match(r"^.+?\s+hiring\s+(?P<role>.+?)(?:\s+in\s+(?P<loc>[^|]+?))?\s*(?:\|\s*LinkedIn)?$", t, re.I)
    if m:
        return m.group("role").strip(" -|"), (m.group("loc") or "").strip()
    t = _SITE_SUFFIX.sub("", t)
    t = re.sub(r"^(?:job application for|apply for|hiring)\s+", "", t, flags=re.I)
    t = re.sub(rf"\s+(?:at|@)\s+{re.escape(company)}\b.*$", "", t, flags=re.I)
    t = re.sub(rf"\s*[-–—|]\s*{re.escape(company)}\b.*$", "", t, flags=re.I)
    return t.split(" - ")[0].split(" | ")[0].strip(" -|"), ""


def result_to_job(r: dict, company: str, aliases: list[str], domain: str) -> Optional[JobPosting]:
    url = r.get("href") or r.get("url") or ""
    title_raw, body = r.get("title", ""), r.get("body", "")
    source = next((k for k, pat in _PORTALS if pat.search(url)), "")
    if not source:
        if not (domain and same_site(url, f"https://{domain}")):
            return None
        segs = [s for s in re.sub(r"^https?://[^/]+", "", url).split("?")[0].split("/") if s]
        if not any(s.lower() in ("job", "jobs", "career", "careers", "position", "openings", "role", "roles") for s in segs[:-1]):
            return None
        source = "web"
    else:
        blob = f"{title_raw} {body} {url}".lower()
        names = [company, *aliases]
        if not any(all(t in blob for t in name_tokens(n)) for n in names if name_tokens(n)):
            return None
    role, loc = parse_result_title(title_raw, company)
    if not (3 <= len(role) <= 120) or _LISTING_TITLE.match(role) or role.lower() == company.lower():
        return None
    return JobPosting(
        title=role, company=company, url=url, source=source, location=loc,
        description=" ".join(body.split())[:600], seniority=infer_seniority(role), external_id=url,
    )


class WebSearchSource(JobSource):
    """Individual job pages on LinkedIn / Naukri / Indeed / Wellfound ... that a web search returns for this
    company. Only search-engine results are read; those sites themselves are never scraped."""

    name = "web"
    kind = "aggregator"
    server_side_search = False

    def __init__(self, company: str, aliases: list[str], domain: str, *, search: Optional[Callable[[str, int], list]] = None,
                 enabled: bool = True) -> None:
        self.company, self.aliases, self.domain = company, aliases, domain
        self._search, self.enabled = search, enabled

    def configured(self) -> bool:
        return self.enabled

    def not_configured_hint(self) -> str:
        return "Web search is turned off."

    def _run(self, q: str) -> list[dict]:
        fn = self._search
        if fn is None:
            try:
                from app.tools.web_search import search_web as fn   # type: ignore[assignment]
            except ImportError:
                return []
        try:
            return list(fn(q, 8) or [])
        except Exception:  # noqa: BLE001 - search is best effort
            return []

    async def fetch(self, ctx: SourceContext, f: SearchFilters) -> list[JobPosting]:
        key = f"websearch:{self.company.lower()}:{f.q.lower()}"
        cached = ctx.cache.get(key)
        if cached is not None:
            return cached
        c, role = self.company, f.q.strip()
        queries = [
            f'"{c}" {role} jobs'.replace("  ", " "),
            f'{c} {role} jobs site:linkedin.com/jobs'.replace("  ", " "),
            f'{c} {role} jobs site:naukri.com'.replace("  ", " "),
            f'{c} {role} jobs wellfound OR workatastartup OR instahyre OR indeed'.replace("  ", " "),
        ]
        batches = await asyncio.gather(*[asyncio.to_thread(self._run, q) for q in queries])
        seen: set[str] = set()
        out: list[JobPosting] = []
        for batch in batches:
            for r in batch:
                j = result_to_job(r, c, self.aliases, self.domain)
                if j and j.url not in seen:
                    seen.add(j.url)
                    out.append(j)
        ctx.cache.set(key, out, ctx.cache_ttl)
        return [dataclasses.replace(j, also_on=[]) for j in out]
