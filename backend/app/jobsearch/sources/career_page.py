"""Direct company career pages that publish schema.org `JobPosting` JSON-LD (Google-for-Jobs markup)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterator
from urllib.parse import urlparse

from app.jobsearch.posting import JobPosting, SearchFilters
from app.jobsearch.sources.base import (
    JobSource, SourceContext, SourceNotConfigured, annualize, parse_dt, split_list,
)
from app.jobsearch.text import html_to_text, infer_seniority, parse_experience

logger = logging.getLogger("careerprep.jobs")

_LD_RE = re.compile(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.I | re.S)


def _walk(node: Any) -> Iterator[dict]:
    if isinstance(node, list):
        for n in node:
            yield from _walk(n)
    elif isinstance(node, dict):
        t = node.get("@type")
        types = t if isinstance(t, list) else [t]
        if "JobPosting" in types:
            yield node
        for k in ("@graph", "itemListElement", "item", "mainEntity"):
            if k in node:
                yield from _walk(node[k])


def _loc(node: dict) -> str:
    locs = node.get("jobLocation")
    locs = locs if isinstance(locs, list) else [locs] if locs else []
    parts = []
    for l in locs:
        a = (l or {}).get("address") or {}
        if isinstance(a, str):
            parts.append(a)
            continue
        bits = [a.get("addressLocality"), a.get("addressRegion"), a.get("addressCountry") if isinstance(a.get("addressCountry"), str) else None]
        parts.append(", ".join(b for b in bits if b))
    return " | ".join(p for p in parts if p)


def parse_job_postings(html_text: str, page_url: str) -> list[JobPosting]:
    host = urlparse(page_url).netloc.replace("www.", "")
    default_company = host.split(".")[0].capitalize() if host else ""
    out: list[JobPosting] = []
    for raw in _LD_RE.findall(html_text or ""):
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        for n in _walk(data):
            title = (n.get("title") or "").strip()
            if not title:
                continue
            org = n.get("hiringOrganization") or {}
            company = (org.get("name") if isinstance(org, dict) else str(org)) or default_company
            desc = html_to_text(n.get("description"))
            sal = ((n.get("baseSalary") or {}).get("value") or {}) if isinstance(n.get("baseSalary"), dict) else {}
            cur = (n.get("baseSalary") or {}).get("currency", "") if isinstance(n.get("baseSalary"), dict) else ""
            remote = "telecommute" in str(n.get("jobLocationType") or "").lower()
            exp = parse_experience(desc)
            et = n.get("employmentType")
            et = (et[0] if isinstance(et, list) and et else et) or ""
            url = n.get("url") or n.get("sameAs") or page_url
            out.append(JobPosting(
                title=title, company=company, url=url, source="career_page",
                location=_loc(n), remote=remote, work_mode="remote" if remote else "",
                posted_at=parse_dt(n.get("datePosted")),
                description=desc,
                employment_type=str(et).lower().replace("_", "-"),
                seniority=infer_seniority(title),
                experience_min=exp[0], experience_max=exp[1],
                salary_min=annualize(_num(sal.get("minValue")), sal.get("unitText")),
                salary_max=annualize(_num(sal.get("maxValue")), sal.get("unitText")),
                salary_currency=cur if isinstance(cur, str) else "",
                external_id=str(n.get("identifier", {}).get("value") if isinstance(n.get("identifier"), dict) else url),
            ))
    return out


def _num(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


class CareerPageSource(JobSource):
    name = "career_page"
    kind = "career_page"
    server_side_search = False

    def __init__(self, urls: str | list[str]) -> None:
        self.urls = split_list(urls) if isinstance(urls, str) else list(urls)

    def configured(self) -> bool:
        return bool(self.urls)

    def not_configured_hint(self) -> str:
        return "Set JOB_CAREER_PAGE_URLS to company career-page URLs that publish JobPosting JSON-LD."

    async def fetch(self, ctx: SourceContext, f: SearchFilters) -> list[JobPosting]:
        if not self.urls:
            raise SourceNotConfigured(self.not_configured_hint())
        jobs: list[JobPosting] = []
        for url in self.urls:
            key = f"career_page:{url}"
            cached = ctx.cache.get(key)
            if cached is None:
                try:
                    r = await ctx.client.get(url, headers={"Accept": "text/html"})
                    r.raise_for_status()
                    cached = parse_job_postings(r.text, url)
                except Exception as exc:  # noqa: BLE001 - one bad page must not hide the rest
                    logger.info("career page %s skipped: %s", url, type(exc).__name__)
                    continue
                ctx.cache.set(key, cached, ctx.cache_ttl)
            jobs.extend(cached)
        return jobs
