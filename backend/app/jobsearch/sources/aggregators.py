"""Licensed / free aggregator APIs. These are how LinkedIn, Indeed, Naukri-style listings arrive:
those portals have no public search API and forbid scraping, so we never scrape them."""

from __future__ import annotations

import logging
from typing import Any

from app.jobsearch.posting import JobPosting, SearchFilters, classify_publisher
from app.jobsearch.sources.base import (
    JobSource, SourceContext, SourceNotConfigured, annualize, parse_dt,
)
from app.jobsearch.text import html_to_text, infer_seniority, parse_experience

logger = logging.getLogger("careerprep.jobs")

_ADZUNA_CURRENCY = {"in": "INR", "us": "USD", "gb": "GBP", "ca": "CAD", "au": "AUD", "de": "EUR",
                    "fr": "EUR", "nl": "EUR", "sg": "SGD", "nz": "NZD", "br": "BRL", "pl": "PLN"}


def _f(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


class AdzunaSource(JobSource):
    """https://developer.adzuna.com/  - free key, good India coverage, structured salary."""
    name = "adzuna"
    kind = "aggregator"
    server_side_search = True

    def __init__(self, app_id: str, app_key: str) -> None:
        self.app_id, self.app_key = app_id, app_key

    def configured(self) -> bool:
        return bool(self.app_id and self.app_key)

    def not_configured_hint(self) -> str:
        return "Set ADZUNA_APP_ID and ADZUNA_APP_KEY (free at developer.adzuna.com)."

    async def fetch(self, ctx: SourceContext, f: SearchFilters) -> list[JobPosting]:
        if not self.configured():
            raise SourceNotConfigured(self.not_configured_hint())
        country = (f.country or ctx.default_country or "in").lower()
        params: dict[str, Any] = {
            "app_id": self.app_id, "app_key": self.app_key, "results_per_page": 50,
            "sort_by": "date", "content-type": "application/json",
        }
        if f.q:
            params["what"] = f.q
        if f.location:
            params["where"] = f.location
        if f.posted_within_days:
            params["max_days_old"] = f.posted_within_days
        if f.salary_min and (not f.salary_currency or f.salary_currency == _ADZUNA_CURRENCY.get(country)):
            params["salary_min"] = int(f.salary_min)
        if f.employment_type == "full-time":
            params["full_time"] = 1
        elif f.employment_type == "part-time":
            params["part_time"] = 1
        elif f.employment_type == "contract":
            params["contract"] = 1
        r = await ctx.client.get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1", params=params)
        r.raise_for_status()
        out = []
        for j in r.json().get("results", []):
            title = j.get("title") or ""
            desc = html_to_text(j.get("description"))
            exp = parse_experience(f"{title}. {desc}")
            out.append(JobPosting(
                title=title,
                company=(j.get("company") or {}).get("display_name") or "",
                url=j.get("redirect_url") or "",
                source="adzuna",
                location=(j.get("location") or {}).get("display_name") or "",
                posted_at=parse_dt(j.get("created")),
                description=desc,
                employment_type=(f"{j.get('contract_time') or ''}".replace("_", "-")),
                seniority=infer_seniority(title),
                experience_min=exp[0], experience_max=exp[1],
                salary_min=_f(j.get("salary_min")), salary_max=_f(j.get("salary_max")),
                salary_currency=_ADZUNA_CURRENCY.get(country, "") if j.get("salary_min") else "",
                external_id=str(j.get("id") or ""),
            ))
        return out


class JSearchSource(JobSource):
    """RapidAPI JSearch: Google-for-Jobs index, includes LinkedIn / Indeed / Glassdoor / Naukri-style publishers."""
    name = "jsearch"
    kind = "aggregator"
    server_side_search = True

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def configured(self) -> bool:
        return bool(self.api_key)

    def not_configured_hint(self) -> str:
        return "Set JSEARCH_API_KEY (RapidAPI 'JSearch') to get LinkedIn / Indeed / Glassdoor listings."

    async def fetch(self, ctx: SourceContext, f: SearchFilters) -> list[JobPosting]:
        if not self.configured():
            raise SourceNotConfigured(self.not_configured_hint())
        query = f.q or "jobs"
        if f.location:
            query += f" in {f.location}"
        params: dict[str, Any] = {"query": query, "page": 1, "num_pages": 1,
                                  "country": (f.country or ctx.default_country or "in").lower()}
        if f.work_mode == "remote":
            params["remote_jobs_only"] = "true"
        if f.posted_within_days:
            params["date_posted"] = ("today" if f.posted_within_days <= 1 else "3days" if f.posted_within_days <= 3
                                     else "week" if f.posted_within_days <= 7 else "month")
        et = {"full-time": "FULLTIME", "part-time": "PARTTIME", "contract": "CONTRACTOR", "internship": "INTERN"}.get(f.employment_type)
        if et:
            params["employment_types"] = et
        r = await ctx.client.get(
            "https://jsearch.p.rapidapi.com/search", params=params,
            headers={"X-RapidAPI-Key": self.api_key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"},
        )
        r.raise_for_status()
        out = []
        for j in r.json().get("data", []):
            title = j.get("job_title") or ""
            desc = j.get("job_description") or ""
            publisher = j.get("job_publisher") or ""
            months = ((j.get("job_required_experience") or {}).get("required_experience_in_months"))
            exp_min = months / 12.0 if isinstance(months, (int, float)) and months else None
            exp = parse_experience(desc)
            loc = ", ".join(x for x in (j.get("job_city"), j.get("job_state"), j.get("job_country")) if x)
            remote = bool(j.get("job_is_remote"))
            out.append(JobPosting(
                title=title,
                company=j.get("employer_name") or "",
                url=j.get("job_apply_link") or "",
                source=classify_publisher(publisher),
                location=loc,
                remote=remote, work_mode="remote" if remote else "",
                posted_at=parse_dt(j.get("job_posted_at_datetime_utc")),
                description=desc[:20000],
                employment_type=(j.get("job_employment_type") or "").lower().replace("fulltime", "full-time")
                                .replace("parttime", "part-time").replace("contractor", "contract"),
                seniority=infer_seniority(title),
                experience_min=exp_min if exp_min is not None else exp[0], experience_max=exp[1],
                salary_min=annualize(_f(j.get("job_min_salary")), j.get("job_salary_period")),
                salary_max=annualize(_f(j.get("job_max_salary")), j.get("job_salary_period")),
                salary_currency=j.get("job_salary_currency") or "",
                external_id=str(j.get("job_id") or ""),
            ))
        return out


class JoobleSource(JobSource):
    """https://jooble.org/api/about - free key; aggregates many portals incl. Naukri-style sites."""
    name = "jooble"
    kind = "aggregator"
    server_side_search = True

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def configured(self) -> bool:
        return bool(self.api_key)

    def not_configured_hint(self) -> str:
        return "Set JOOBLE_API_KEY (free at jooble.org/api/about)."

    async def fetch(self, ctx: SourceContext, f: SearchFilters) -> list[JobPosting]:
        if not self.configured():
            raise SourceNotConfigured(self.not_configured_hint())
        body: dict[str, Any] = {"keywords": f.q or "", "location": f.location or "", "page": 1}
        if f.salary_min:
            body["salary"] = int(f.salary_min)
        r = await ctx.client.post(f"https://jooble.org/api/{self.api_key}", json=body)
        r.raise_for_status()
        out = []
        for j in r.json().get("jobs", []):
            title = html_to_text(j.get("title"))
            desc = html_to_text(j.get("snippet"))
            exp = parse_experience(f"{title}. {desc}")
            loc = j.get("location") or ""
            out.append(JobPosting(
                title=title,
                company=j.get("company") or "",
                url=j.get("link") or "",
                source=classify_publisher(j.get("source")) if classify_publisher(j.get("source")) != "other" else "jooble",
                location=loc,
                remote="remote" in loc.lower(), work_mode="remote" if "remote" in loc.lower() else "",
                posted_at=parse_dt(j.get("updated")),
                description=desc,
                employment_type=(j.get("type") or "").lower().replace("_", "-"),
                seniority=infer_seniority(title),
                experience_min=exp[0], experience_max=exp[1],
                salary_text=j.get("salary") or "",
                external_id=str(j.get("id") or ""),
            ))
        return out


class RemotiveSource(JobSource):
    """https://remotive.com/api/remote-jobs - no key, remote only. Off by default (they ask for sparse polling)."""
    name = "remotive"
    kind = "aggregator"
    server_side_search = True

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def configured(self) -> bool:
        return self.enabled

    def not_configured_hint(self) -> str:
        return "Set JOB_REMOTIVE_ENABLED=true for remote-only jobs from Remotive."

    async def fetch(self, ctx: SourceContext, f: SearchFilters) -> list[JobPosting]:
        if not self.enabled:
            raise SourceNotConfigured(self.not_configured_hint())
        if f.work_mode in ("onsite", "hybrid"):
            return []
        key = f"remotive:{(f.q or '').lower()}"
        cached = ctx.cache.get(key)
        if cached is not None:
            return cached
        r = await ctx.client.get("https://remotive.com/api/remote-jobs", params={"search": f.q or "", "limit": 50})
        r.raise_for_status()
        out = []
        for j in r.json().get("jobs", []):
            title = j.get("title") or ""
            desc = html_to_text(j.get("description"))
            exp = parse_experience(desc)
            out.append(JobPosting(
                title=title, company=j.get("company_name") or "", url=j.get("url") or "",
                source="remotive", location=j.get("candidate_required_location") or "Remote",
                remote=True, work_mode="remote",
                posted_at=parse_dt(j.get("publication_date")),
                description=desc,
                employment_type=(j.get("job_type") or "").lower().replace("_", "-"),
                seniority=infer_seniority(title),
                experience_min=exp[0], experience_max=exp[1],
                salary_text=j.get("salary") or "",
                external_id=str(j.get("id") or ""),
            ))
        ctx.cache.set(key, out, max(ctx.cache_ttl, 6 * 3600))
        return out
