"""Official public job-board APIs: Greenhouse, Lever, Ashby. No API keys, no scraping."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.jobsearch.posting import JobPosting, SearchFilters
from app.jobsearch.sources.base import (
    JobSource, SourceContext, SourceNotConfigured, annualize, parse_dt, split_list, title_case_slug,
)
from app.jobsearch.text import html_to_text, infer_seniority, parse_experience

logger = logging.getLogger("careerprep.jobs")


class _BoardSource(JobSource):
    kind = "ats"
    server_side_search = False
    setting_hint = ""

    def __init__(self, boards: str | list[str]) -> None:
        self.boards = split_list(boards) if isinstance(boards, str) else list(boards)

    def configured(self) -> bool:
        return bool(self.boards)

    def not_configured_hint(self) -> str:
        return self.setting_hint

    async def fetch(self, ctx: SourceContext, f: SearchFilters) -> list[JobPosting]:
        if not self.boards:
            raise SourceNotConfigured(self.setting_hint)
        results = await asyncio.gather(*[self._board(ctx, b) for b in self.boards], return_exceptions=True)
        jobs: list[JobPosting] = []
        failed = 0
        for b, r in zip(self.boards, results):
            if isinstance(r, Exception):
                failed += 1
                logger.info("%s board %r skipped: %s", self.name, b, type(r).__name__)
                continue
            jobs.extend(r)
        if failed == len(self.boards):
            raise RuntimeError(f"all {failed} {self.name} boards failed")
        return jobs

    async def _board(self, ctx: SourceContext, board: str) -> list[JobPosting]:
        key = f"{self.name}:{board}"
        cached = ctx.cache.get(key)
        if cached is not None:
            return cached
        jobs = await self._download(ctx, board)
        ctx.cache.set(key, jobs, ctx.cache_ttl)
        return jobs

    async def _download(self, ctx: SourceContext, board: str) -> list[JobPosting]:  # pragma: no cover
        raise NotImplementedError


def _mode(is_remote: bool | None, text: str = "") -> str:
    t = (text or "").lower()
    if "hybrid" in t:
        return "hybrid"
    if is_remote or "remote" in t:
        return "remote"
    return ""


class GreenhouseSource(_BoardSource):
    name = "greenhouse"
    setting_hint = "Set JOB_GREENHOUSE_BOARDS (e.g. stripe,airbnb)."

    async def _download(self, ctx: SourceContext, board: str) -> list[JobPosting]:
        r = await ctx.client.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", params={"content": "true"})
        r.raise_for_status()
        out = []
        for j in r.json().get("jobs", []):
            desc = html_to_text(j.get("content"))
            loc = (j.get("location") or {}).get("name") or ""
            title = j.get("title") or ""
            exp = parse_experience(desc)
            pay_lo, pay_hi, pay_cur = _greenhouse_pay(j)
            out.append(JobPosting(
                title=title,
                company=j.get("company_name") or title_case_slug(board),
                url=j.get("absolute_url") or "",
                source="greenhouse",
                location=loc,
                remote=_mode(None, loc) == "remote",
                work_mode=_mode(None, loc),
                posted_at=parse_dt(j.get("first_published") or j.get("updated_at")),
                description=desc,
                seniority=infer_seniority(title),
                experience_min=exp[0], experience_max=exp[1],
                salary_min=pay_lo, salary_max=pay_hi, salary_currency=pay_cur,
                external_id=str(j.get("id") or ""),
            ))
        return out


def _greenhouse_pay(j: dict[str, Any]) -> tuple[float | None, float | None, str]:
    for rng in j.get("pay_input_ranges") or []:
        try:
            lo = float(rng["min_cents"]) / 100 if rng.get("min_cents") is not None else None
            hi = float(rng["max_cents"]) / 100 if rng.get("max_cents") is not None else None
            return lo, hi, rng.get("currency_type") or ""
        except (KeyError, TypeError, ValueError):
            continue
    return None, None, ""


class LeverSource(_BoardSource):
    name = "lever"
    setting_hint = "Set JOB_LEVER_COMPANIES (e.g. palantir,spotify)."

    async def _download(self, ctx: SourceContext, board: str) -> list[JobPosting]:
        r = await ctx.client.get(f"https://api.lever.co/v0/postings/{board}", params={"mode": "json"})
        r.raise_for_status()
        out = []
        for j in r.json():
            cats = j.get("categories") or {}
            title = j.get("text") or ""
            desc = j.get("descriptionPlain") or html_to_text(j.get("description"))
            wp = (j.get("workplaceType") or "").lower()
            loc = cats.get("location") or ", ".join(cats.get("allLocations") or []) or ""
            sal = j.get("salaryRange") or {}
            exp = parse_experience(desc)
            out.append(JobPosting(
                title=title,
                company=title_case_slug(board),
                url=j.get("hostedUrl") or j.get("applyUrl") or "",
                source="lever",
                location=loc,
                remote=wp == "remote",
                work_mode=wp if wp in ("remote", "hybrid", "onsite") else _mode(None, loc),
                posted_at=parse_dt(j.get("createdAt")),
                description=desc,
                employment_type=(cats.get("commitment") or "").lower(),
                seniority=infer_seniority(title),
                experience_min=exp[0], experience_max=exp[1],
                salary_min=annualize(sal.get("min"), sal.get("interval")),
                salary_max=annualize(sal.get("max"), sal.get("interval")),
                salary_currency=sal.get("currency") or "",
                external_id=str(j.get("id") or ""),
            ))
        return out


class AshbySource(_BoardSource):
    name = "ashby"
    setting_hint = "Set JOB_ASHBY_BOARDS (e.g. notion,ramp)."

    async def _download(self, ctx: SourceContext, board: str) -> list[JobPosting]:
        r = await ctx.client.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{board}", params={"includeCompensation": "true"}
        )
        r.raise_for_status()
        out = []
        for j in r.json().get("jobs", []):
            if j.get("isListed") is False:
                continue
            title = j.get("title") or ""
            desc = j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml"))
            lo = hi = None
            cur = ""
            for comp in ((j.get("compensation") or {}).get("summaryComponents") or []):
                if (comp.get("compensationType") or "").lower() == "salary":
                    lo = annualize(comp.get("minValue"), comp.get("interval"))
                    hi = annualize(comp.get("maxValue"), comp.get("interval"))
                    cur = comp.get("currencyCode") or ""
                    break
            exp = parse_experience(desc)
            loc = j.get("location") or ""
            mode = "remote" if j.get("isRemote") else _mode(None, loc)
            out.append(JobPosting(
                title=title,
                company=title_case_slug(board),
                url=j.get("jobUrl") or j.get("applyUrl") or "",
                source="ashby",
                location=loc,
                remote=mode == "remote",
                work_mode=mode,
                posted_at=parse_dt(j.get("publishedAt")),
                description=desc,
                employment_type=(j.get("employmentType") or "").lower().replace("fulltime", "full-time"),
                seniority=infer_seniority(title),
                experience_min=exp[0], experience_max=exp[1],
                salary_min=lo, salary_max=hi, salary_currency=cur,
                external_id=str(j.get("id") or ""),
            ))
        return out
