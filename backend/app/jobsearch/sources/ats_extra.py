"""More public job-board APIs used by startups: Workable, SmartRecruiters, Recruitee.

Same contract as the Greenhouse / Lever / Ashby sources in `ats.py`. Parsing is defensive: a field that
is missing or shaped differently yields an empty value, never an exception.
"""

from __future__ import annotations

from typing import Any

from app.jobsearch.posting import JobPosting
from app.jobsearch.sources.ats import _BoardSource, _mode
from app.jobsearch.sources.base import SourceContext, parse_dt, title_case_slug
from app.jobsearch.text import html_to_text, infer_seniority, parse_experience


def _s(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _type(v: Any) -> str:
    t = _s(v).lower().replace("_", "-").replace(" ", "-")
    return {"fulltime": "full-time", "full-time": "full-time", "parttime": "part-time", "part-time": "part-time",
            "contract": "contract", "contractor": "contract", "temporary": "contract", "internship": "internship",
            "intern": "internship"}.get(t, t)


def parse_workable(data: dict, slug: str) -> list[JobPosting]:
    company = _s(data.get("name")) or title_case_slug(slug)
    out: list[JobPosting] = []
    for j in data.get("jobs") or []:
        if not isinstance(j, dict):
            continue
        title = _s(j.get("title"))
        url = _s(j.get("url")) or _s(j.get("shortlink")) or _s(j.get("application_url"))
        if not title or not url:
            continue
        locs = j.get("locations") if isinstance(j.get("locations"), list) else []
        loc = ", ".join(x for x in (_s(j.get("city")), _s(j.get("state")), _s(j.get("country"))) if x)
        if not loc and locs and isinstance(locs[0], dict):
            loc = ", ".join(x for x in (_s(locs[0].get("city")), _s(locs[0].get("region")), _s(locs[0].get("country"))) if x)
        remote = bool(j.get("telecommuting"))
        desc = html_to_text(j.get("description"))
        exp = parse_experience(desc)
        out.append(JobPosting(
            title=title, company=company, url=url, source="workable", location=loc, remote=remote,
            work_mode="remote" if remote else _mode(None, loc),
            posted_at=parse_dt(j.get("published_on") or j.get("created_at")),
            description=desc, employment_type=_type(j.get("employment_type")),
            seniority=infer_seniority(title), experience_min=exp[0], experience_max=exp[1],
            external_id=_s(j.get("shortcode")) or url,
        ))
    return out


def parse_smartrecruiters(data: dict, slug: str) -> list[JobPosting]:
    out: list[JobPosting] = []
    for j in data.get("content") or []:
        if not isinstance(j, dict):
            continue
        title, pid = _s(j.get("name")), _s(j.get("id"))
        if not title or not pid:
            continue
        comp = j.get("company") if isinstance(j.get("company"), dict) else {}
        ident = _s(comp.get("identifier")) or slug
        loc_d = j.get("location") if isinstance(j.get("location"), dict) else {}
        loc = _s(loc_d.get("fullLocation")) or ", ".join(
            x for x in (_s(loc_d.get("city")), _s(loc_d.get("region")), _s(loc_d.get("country")).upper()) if x)
        remote = bool(loc_d.get("remote"))
        toe = j.get("typeOfEmployment") if isinstance(j.get("typeOfEmployment"), dict) else {}
        out.append(JobPosting(
            title=title, company=_s(comp.get("name")) or title_case_slug(slug),
            url=f"https://jobs.smartrecruiters.com/{ident}/{pid}", source="smartrecruiters",
            location=loc, remote=remote, work_mode="remote" if remote else _mode(None, loc),
            posted_at=parse_dt(j.get("releasedDate")),
            employment_type=_type(toe.get("label") or toe.get("id")),
            seniority=infer_seniority(title), external_id=pid,
        ))
    return out


def parse_recruitee(data: dict, slug: str) -> list[JobPosting]:
    out: list[JobPosting] = []
    for j in data.get("offers") or []:
        if not isinstance(j, dict) or j.get("status") not in (None, "published"):
            continue
        title = _s(j.get("title"))
        url = _s(j.get("careers_url")) or _s(j.get("careers_apply_url"))
        if not title or not url:
            continue
        loc = _s(j.get("location")) or ", ".join(x for x in (_s(j.get("city")), _s(j.get("country"))) if x)
        remote = bool(j.get("remote"))
        desc = html_to_text(f"{j.get('description') or ''} {j.get('requirements') or ''}")
        exp = parse_experience(desc)
        out.append(JobPosting(
            title=title, company=_s(j.get("company_name")) or title_case_slug(slug), url=url, source="recruitee",
            location=loc, remote=remote, work_mode="remote" if remote else _mode(None, loc),
            posted_at=parse_dt(j.get("published_at") or j.get("created_at")),
            description=desc, employment_type=_type(j.get("employment_type_code")),
            seniority=infer_seniority(title), experience_min=exp[0], experience_max=exp[1],
            external_id=str(j.get("id") or url),
        ))
    return out


class WorkableSource(_BoardSource):
    name = "workable"
    setting_hint = "Workable boards are discovered per company."

    async def _download(self, ctx: SourceContext, board: str) -> list[JobPosting]:
        r = await ctx.client.get(f"https://apply.workable.com/api/v1/widget/accounts/{board}", params={"details": "true"})
        r.raise_for_status()
        return parse_workable(r.json(), board)


class SmartRecruitersSource(_BoardSource):
    name = "smartrecruiters"
    setting_hint = "SmartRecruiters boards are discovered per company."

    async def _download(self, ctx: SourceContext, board: str) -> list[JobPosting]:
        out: list[JobPosting] = []
        for offset in range(0, 300, 100):
            r = await ctx.client.get(
                f"https://api.smartrecruiters.com/v1/companies/{board}/postings", params={"limit": 100, "offset": offset})
            r.raise_for_status()
            data = r.json()
            out.extend(parse_smartrecruiters(data, board))
            if offset + 100 >= int(data.get("totalFound") or 0):
                break
        return out


class RecruiteeSource(_BoardSource):
    name = "recruitee"
    setting_hint = "Recruitee boards are discovered per company."

    async def _download(self, ctx: SourceContext, board: str) -> list[JobPosting]:
        r = await ctx.client.get(f"https://{board}.recruitee.com/api/offers/")
        r.raise_for_status()
        return parse_recruitee(r.json(), board)
