"""Company search: identify the company and summarise it (`lookup_company`), then collect its jobs from
every place we can reach (`company_jobs`)."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlparse

from app.core.config import Settings, get_settings
from app.jobsearch import service as jobs_service
from app.jobsearch.company.careers import CareerReport, scrape_career_page
from app.jobsearch.company.discover import (
    COMMON_CAREER_PATHS, AtsBoard, PageInfo, absolute, detect_boards, find_career_links, looks_like_careers_page,
    parse_organization, parse_page,
)
from app.jobsearch.company.identify import (
    browse_links, clean_name, company_key, core, domain_name_score, domain_of, guess_domains, looks_like_url,
    name_tokens, normalize_url, pick_sites, registrable_domain, slug_candidates, to_url,
)
from app.jobsearch.company.linkedin import LinkedInCompany, pick_linkedin
from app.jobsearch.company.net import safe_get, text_of
from app.jobsearch.company.overview import LlmFn, build_overview, wiki_relevant
from app.jobsearch.company.profile import CompanyProfile
from app.jobsearch.company.sources import (
    CareerScrapeSource, ScopedSource, WebSearchSource, board_sources, probe_boards,
)
from app.jobsearch.matching import CandidateProfileView
from app.jobsearch.posting import SearchFilters
from app.jobsearch.service import SearchResult, search_jobs
from app.jobsearch.sources.base import SourceContext, TTLCache

logger = logging.getLogger("careerprep.jobs")

_profiles = TTLCache(max_entries=300)
_HTML = {"Accept": "text/html,application/xhtml+xml"}
_LEGAL_TAIL = re.compile(r"[,\s]+(?:inc|llc|ltd|limited|pvt|private|plc|corp|corporation|gmbh|co)\.?(?:[,\s]+(?:ltd|limited|pvt|inc)\.?)*$", re.I)


class CompanyNotFound(Exception):
    """Nothing usable was found for the query."""


@dataclass
class Toolbox:
    """The blocking research tools, injectable for tests."""

    search: Callable[[str, int], list]
    wikipedia: Callable[[str], tuple]
    llm: Optional[LlmFn] = None


def default_toolbox() -> Toolbox:
    def search(q: str, n: int = 5) -> list:
        try:
            from app.tools.web_search import search_web
        except ImportError:
            return []
        return search_web(q, n)

    def wiki(name: str) -> tuple:
        try:
            from app.tools.wikipedia import wikipedia_summary
        except ImportError:
            return "", ""
        return wikipedia_summary(name)

    return Toolbox(search=search, wikipedia=wiki)


def _ctx(settings: Settings) -> SourceContext:
    return SourceContext(
        client=jobs_service.get_client(), cache=jobs_service._cache,    # noqa: SLF001 - share the main search's cache
        cache_ttl=float(settings.job_cache_ttl_seconds), default_country=settings.job_default_country,
    )


def pretty_name(raw: str) -> str:
    n = _LEGAL_TAIL.sub("", (raw or "").strip()).strip(" ,|-")
    return n


async def _get_page(ctx: SourceContext, url: str) -> tuple[str, PageInfo, str] | None:
    """(final_url, parsed page, html) or None."""
    try:
        r = await safe_get(ctx.client, url, headers=_HTML)
    except Exception as exc:  # noqa: BLE001
        logger.info("fetch %s failed: %s", url, type(exc).__name__)
        return None
    if r is None or r.status_code >= 400:
        return None
    html = text_of(r)
    if not html:
        return None
    return str(getattr(r, "url", url)), parse_page(html), html


async def _find_site_by_guess(ctx: SourceContext, name: str) -> Optional[str]:
    """Search found nothing usable: try name.com / name.io / ... and keep one whose page names the company."""
    toks = name_tokens(name)

    async def one(dom: str) -> Optional[str]:
        got = await _get_page(ctx, f"https://{dom}/")
        if not got:
            return None
        url, page, _ = got
        blob = f"{page.title} {page.meta.get('og:site_name', '')} {page.meta.get('description', '')}".lower()
        return url if toks and all(t in blob for t in toks) else None

    for res in await asyncio.gather(*[one(d) for d in guess_domains(name)]):
        if res:
            return res
    return None


async def _probe_career_paths(ctx: SourceContext, base_url: str) -> str:
    p = urlparse(base_url)
    root = registrable_domain(p.hostname or "")
    urls = [f"{p.scheme}://{p.netloc}{path}" for path in COMMON_CAREER_PATHS]
    urls += [f"https://careers.{root}/", f"https://jobs.{root}/"]
    sem = asyncio.Semaphore(6)

    async def one(u: str) -> Optional[str]:
        async with sem:
            got = await _get_page(ctx, u)
        return got[0] if got and looks_like_careers_page(got[1]) else None

    for res in await asyncio.gather(*[one(u) for u in urls]):
        if res:
            return res
    return ""


def _derive_name(query: str, org: dict, home: Optional[PageInfo], domain: str, from_url: bool) -> str:
    if not from_url:
        return clean_name(query) if not clean_name(query).islower() else clean_name(query).title()
    for cand in (org.get("name"), home and home.meta.get("og:site_name"), home and home.title.split("|")[0].split(" - ")[0].strip()):
        cand = pretty_name(cand or "")
        if 2 <= len(cand) <= 60:
            return cand
    return domain.split(".")[0].replace("-", " ").title()


def _hint_boards(results: list, name: str, li: Optional[LinkedInCompany]) -> list[AtsBoard]:
    """ATS boards that search results point to, kept only when the slug looks like this company.
    They are verified against the postings before use (see `probe_boards`)."""
    c = core(name)
    out: list[AtsBoard] = []
    for b in detect_boards(*[r.get("href", "") for r in results or []]):
        s = core(b.slug)
        close = bool(c) and (s == c or (len(c) >= 4 and len(s) >= 4 and (c in s or s in c)))
        if close or (li and b.slug.lower() == li.slug):
            out.append(b)
    return out[:6]


async def lookup_company(
    query: str, *, website: str = "", settings: Optional[Settings] = None, tools: Optional[Toolbox] = None,
) -> CompanyProfile:
    s = settings or get_settings()
    q = clean_name(query)
    if len(q) < 2:
        raise CompanyNotFound("Enter a company name or website.")
    website = website.strip() if website and looks_like_url(website) else ""
    ck = f"company:{q.lower()}|{website.lower()}"
    cached = _profiles.get(ck)
    if cached is not None:
        return cached

    tools = tools or default_toolbox()
    ctx = _ctx(s)
    notes: list[str] = []
    alternatives: list[dict] = []
    from_url = looks_like_url(q)
    site_url = to_url(q) if from_url else (to_url(website) if website else "")
    confidence = "high" if site_url else "low"

    li_results: Optional[list] = None
    ats_results: Optional[list] = None
    if not site_url:
        # website, LinkedIn page and job-board hits are independent searches: run them together
        results, li_results, ats_results = await asyncio.gather(
            asyncio.to_thread(tools.search, f"{q} official website", 8),
            asyncio.to_thread(tools.search, f"site:linkedin.com/company {q}", 8),
            asyncio.to_thread(tools.search, f'"{q}" careers jobs', 8),
        )
        sites = pick_sites(results, q)
        early_li = (pick_linkedin(li_results, q) or [None])[0]
        if sites:
            site_url = sites[0].url
            confidence = "high" if domain_name_score(sites[0].domain, q) >= 2 else "medium"
            alternatives = [{"name": x.title.split(" - ")[0].split(" | ")[0][:60] or x.domain, "website": x.url, "domain": x.domain}
                            for x in sites[1:]]
            if early_li and early_li.website and domain_of(early_li.website) != sites[0].domain:
                alternatives.insert(0, {"name": f"{early_li.name} (per LinkedIn)", "website": early_li.website,
                                        "domain": domain_of(early_li.website)})
        elif early_li and early_li.website:
            # tiny startups: search often misses the site, but the LinkedIn page names it
            site_url, confidence = early_li.website, "medium"
        else:
            guess = await _find_site_by_guess(ctx, q)
            if guess:
                site_url, confidence = guess, "medium"
    home_got = await _get_page(ctx, site_url) if site_url else None
    if site_url and not home_got:
        notes.append("The company's website could not be read, so the intro is based on other sources.")
    home_url, home, home_html = home_got if home_got else (site_url, None, "")
    org = parse_organization(home.jsonld) if home else {}
    domain = domain_of(home_url or site_url) if (home_url or site_url) else ""
    name = _derive_name(q, org, home, domain, from_url)
    early = (pick_linkedin(li_results, q) or [None])[0] if li_results is not None else None
    if early and not from_url and q.islower():
        name = pretty_name(early.name) or name           # "acme robotics" -> the properly written name

    # ---- gather evidence and the career page in parallel
    about_url = ""
    if home:
        for a in home.anchors:
            if re.search(r"/(about|about-us|company)/?$", a.href.split("?")[0], re.I) and len(a.text) <= 30:
                about_url = absolute(a.href, home_url)
                break

    async def about() -> str:
        if not about_url:
            return ""
        got = await _get_page(ctx, about_url)
        return got[1].text if got else ""

    async def careers() -> tuple[str, str, list[AtsBoard]]:
        if not home:
            return "", "not_found", []
        links = find_career_links(home, home_url)
        boards = [l.board for l in links if l.board]
        if links:
            # show/scrape the company's own page when there is one; its ATS boards are used separately
            own = [l for l in links if not l.board]
            return (own[0] if own else links[0]).url, "found", boards
        guessed = await _probe_career_paths(ctx, home_url)
        return (guessed, "guessed", boards) if guessed else ("", "not_found", boards)

    async def maybe(done: Optional[list], query: str) -> list:
        return done if done is not None else await asyncio.to_thread(tools.search, query, 8)

    wiki_task = asyncio.to_thread(tools.wikipedia, name)
    snippet_task = asyncio.to_thread(tools.search, f"{name} company founded headquarters what it does", 5)
    ((wiki_text, wiki_url), snippets, about_text, (career_url, career_status, boards), li_results, ats_results) = await asyncio.gather(
        wiki_task, snippet_task, about(), careers(),
        maybe(li_results, f"site:linkedin.com/company {name}"), maybe(ats_results, f'"{name}" careers jobs'),
    )
    li = (pick_linkedin(li_results, name, domain) or [None])[0]
    if not site_url:
        notes.append(
            "We couldn't find an official website for this company, so the details come from its LinkedIn page."
            if li else
            "We couldn't find this company's official website. Check the spelling, or search with its website address (for example acme.com).")
        confidence = "medium" if li else "low"
    hint_boards = _hint_boards(ats_results, name, li)
    if wiki_text and not wiki_relevant(name, wiki_text):
        wiki_text, wiki_url = "", ""
    snippets = [r for r in snippets or [] if domain_name_score(domain_of(r.get("href", "")), name) > 0
                or all(t in f"{r.get('title', '')} {r.get('body', '')}".lower() for t in name_tokens(name))]

    overview, sources = await build_overview(
        name, home_url=home_url or site_url, home=home, org=org, about_text=about_text,
        wiki_text=wiki_text, wiki_url=wiki_url, snippets=snippets, llm=tools.llm, linkedin=li,
    )
    if not overview.summary:
        notes.append("Not much information about this company is available online.")
        if confidence == "high":
            confidence = "medium"

    aliases = [a for a in dict.fromkeys(
        pretty_name(x) for x in (org.get("name"), home and home.meta.get("og:site_name"), q) if x) if a and a.lower() != name.lower()]
    key = company_key(name)
    profile = CompanyProfile(
        key=key, name=name, website=normalize_url(home_url or site_url), domain=domain, logo=org.get("logo", ""),
        overview=overview, career_url=career_url, career_status=career_status, boards=boards,
        sources=sources, alternatives=alternatives, links=browse_links(name, key, li.slug if li else ""), aliases=aliases,
        confidence=confidence, notes=notes, hint_boards=hint_boards, linkedin=li,
    )
    _profiles.set(ck, profile, float(getattr(s, "company_cache_ttl_seconds", 21600)))
    _profiles.set(f"company:{name.lower()}|{profile.website.lower()}", profile, float(getattr(s, "company_cache_ttl_seconds", 21600)))
    return profile


@dataclass
class CompanyJobsResult:
    result: SearchResult
    career: Optional[CareerReport]
    boards: list[AtsBoard]


async def company_jobs(
    profile: CompanyProfile, f: SearchFilters, user_profile: Optional[CandidateProfileView] = None, *,
    page: int = 1, page_size: int = 20, settings: Optional[Settings] = None, search: Optional[Callable[[str, int], list]] = None,
) -> CompanyJobsResult:
    """Every job we can find for this company, filtered/sorted by the same engine as the Jobs page."""
    s = settings or get_settings()
    ctx = _ctx(s)

    # 1. the company's own career page (also reveals which ATS it uses)
    report: Optional[CareerReport] = None
    boards: list[AtsBoard] = list(profile.boards)
    scraped = False
    if profile.career_url:
        budget = float(getattr(s, "company_career_budget_seconds", 30.0))
        try:
            _, report = await asyncio.wait_for(scrape_career_page(ctx, profile.career_url), timeout=budget)
            scraped = True
            boards += [b for b in report.boards if b not in boards]
        except asyncio.TimeoutError:
            report = CareerReport(url=profile.career_url, status="unreachable",
                                  note="The career page took too long to read, so it was skipped.")
        except Exception as exc:  # noqa: BLE001
            logger.info("career scrape failed for %s: %s", profile.name, type(exc).__name__)
            report = CareerReport(url=profile.career_url, status="unreachable", note="The career page could not be read.")

    # 2. no ATS spotted: startups often use one anyway, so try the likely board names
    if not boards:
        bk = f"boards:{profile.key}"
        found = jobs_service._cache.get(bk)    # noqa: SLF001
        if found is None:
            slugs = slug_candidates(profile.name, profile.domain, [profile.linkedin.slug] if profile.linkedin else [])
            found = await probe_boards(ctx, profile.name, profile.domain, slugs, profile.hint_boards)
            jobs_service._cache.set(bk, found, float(s.job_cache_ttl_seconds) * 6)    # noqa: SLF001
        boards = list(found)

    # a page that already failed or timed out is not retried inside the per-source timeout
    career_src = CareerScrapeSource(profile.career_url if scraped else "", profile.name,
                                    hint=(report.note if report else ""))
    sources = [career_src, *board_sources(boards, profile.name)]
    sources += [ScopedSource(a, profile.name, profile.aliases) for a in jobs_service.build_sources(s) if a.kind == "aggregator"]
    sources.append(WebSearchSource(profile.name, profile.aliases, profile.domain, search=search,
                                   enabled=bool(getattr(s, "company_web_search_enabled", True))))

    f.company = ""       # the sources are already scoped to this company
    res = await search_jobs(f, user_profile, page=page, page_size=page_size, settings=s, sources=sources)
    return CompanyJobsResult(result=res, career=career_src.report or report, boards=boards)
