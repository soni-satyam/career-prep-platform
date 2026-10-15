"""Company search.

GET /api/v1/companies/lookup  - identify a company: short intro, founding year, career page, ATS, other portals.
GET /api/v1/companies/jobs    - every job we can find for that company, with the same filters as /jobs/search.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.feature_guard import require_feature
from app.api.job_search import SearchResponse, build_search_response
from app.api.profile import get_latest_profile, profile_view
from app.core.config import get_settings
from app.core.database import get_db
from app.jobsearch.company.service import CompanyNotFound, company_jobs, lookup_company
from app.jobsearch.posting import SearchFilters
from app.models.user import User

router = APIRouter(prefix="/companies", tags=["company-search"])


class AtsOut(BaseModel):
    provider: str
    slug: str


class AlternativeOut(BaseModel):
    name: str
    website: str
    domain: str


class LinkOut(BaseModel):
    label: str
    url: str


class CompanyProfileOut(BaseModel):
    key: str
    name: str
    website: str
    domain: str
    logo: str
    summary: str
    what_it_does: str
    founded: Optional[str]
    headquarters: Optional[str]
    industry: Optional[str]
    career_url: str
    career_status: str                 # found | guessed | not_found
    ats: list[AtsOut]
    sources: list[str]
    alternatives: list[AlternativeOut]
    links: list[LinkOut]
    confidence: str                    # high | medium | low
    notes: list[str]


class CareerPageOut(BaseModel):
    url: str
    status: str    # ok | boards_only | js_rendered | blocked | empty | unreachable
    jobs_found: int
    note: str
    ats: list[AtsOut]


class CompanyJobsResponse(SearchResponse):
    company: str
    career_page: Optional[CareerPageOut] = None


def _profile_out(p) -> CompanyProfileOut:
    o = p.overview
    return CompanyProfileOut(
        key=p.key, name=p.name, website=p.website, domain=p.domain, logo=p.logo,
        summary=o.summary, what_it_does=o.what_it_does, founded=o.founded, headquarters=o.headquarters,
        industry=o.industry, career_url=p.career_url, career_status=p.career_status,
        ats=[AtsOut(provider=b.provider, slug=b.slug) for b in p.boards], sources=p.sources,
        alternatives=[AlternativeOut(**a) for a in p.alternatives], links=[LinkOut(**l) for l in p.links],
        confidence=p.confidence, notes=p.notes,
    )


@router.get("/lookup", response_model=CompanyProfileOut, dependencies=[Depends(require_feature("company_search"))])
async def lookup(
    q: str = Query(..., min_length=2, max_length=120, description="Company name, or its website address"),
    website: str = Query("", max_length=200, description="Pin the company's website when the name is ambiguous"),
    user: User = Depends(get_current_user),
):
    timeout = float(getattr(get_settings(), "company_lookup_timeout_seconds", 25.0))
    try:
        profile = await asyncio.wait_for(lookup_company(q, website=website), timeout=timeout)
    except CompanyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Looking up this company took too long. Please try again.") from exc
    return _profile_out(profile)


@router.get("/jobs", response_model=CompanyJobsResponse, dependencies=[Depends(require_feature("company_search"))])
async def jobs(
    name: str = Query(..., min_length=2, max_length=120, description="Company name, as returned by /lookup"),
    website: str = Query("", max_length=200, description="Company website, as returned by /lookup"),
    q: str = Query("", max_length=120, description="Role / keywords inside this company"),
    location: str = Query("", max_length=120),
    country: str = Query("", max_length=2),
    work_mode: str = Query("", pattern="^(|remote|hybrid|onsite)$"),
    salary_min: Optional[float] = Query(None, ge=0),
    salary_currency: str = Query("", max_length=3),
    include_unspecified_salary: bool = True,
    experience_min: Optional[float] = Query(None, ge=0, le=40),
    experience_max: Optional[float] = Query(None, ge=0, le=40),
    employment_type: str = Query("", pattern="^(|full-time|part-time|contract|internship)$"),
    posted_within_days: Optional[int] = Query(None, ge=1, le=90),
    sources: list[str] = Query(default=[]),
    sort: str = Query("priority", pattern="^(priority|recent|match)$"),
    page: int = Query(1, ge=1, le=50),
    page_size: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        profile = await lookup_company(name, website=website)      # served from cache after /lookup
    except CompanyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    f = SearchFilters(
        q=q.strip(), location=location.strip(), country=country.strip().lower(), work_mode=work_mode,
        salary_min=salary_min, salary_currency=salary_currency.strip().upper(),
        include_unspecified_salary=include_unspecified_salary,
        experience_min=experience_min, experience_max=experience_max,
        employment_type=employment_type, posted_within_days=posted_within_days,
        sources=[s for s in sources if s], sort=sort,
    )
    user_profile = profile_view(await get_latest_profile(db, user), user)
    res = await company_jobs(profile, f, user_profile, page=page, page_size=page_size)
    base = build_search_response(res.result)
    c = res.career
    return CompanyJobsResponse(
        **base.model_dump(), company=profile.name,
        career_page=CareerPageOut(
            url=c.url, status=c.status, jobs_found=c.jobs_found, note=c.note,
            ats=[AtsOut(provider=b.provider, slug=b.slug) for b in res.boards],
        ) if c else None,
    )
