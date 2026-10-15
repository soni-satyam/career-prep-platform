"""GET /api/v1/jobs/search - multi-source job search with filters, priority ordering and match %.

Registered BEFORE the legacy jobs router so '/jobs/search' is not read as '/jobs/{job_id}'.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.feature_guard import require_feature
from app.api.profile import get_latest_profile, profile_view
from app.core.database import get_db
from app.jobsearch.posting import SOURCE_LABELS, SearchFilters, source_label, source_priority
from app.jobsearch.service import SearchResult, search_jobs
from app.jobsearch.text import snippet
from app.models.user import User

router = APIRouter(prefix="/jobs", tags=["job-search"])


class MatchOut(BaseModel):
    score: int
    matched_skills: list[str]
    missing_skills: list[str]


class AlsoOn(BaseModel):
    source: str
    label: str
    url: str


class JobResult(BaseModel):
    id: str
    title: str
    company: str
    location: str
    remote: bool
    work_mode: str
    url: str
    source: str
    source_label: str
    source_tier: int
    posted_at: Optional[datetime]
    snippet: str
    employment_type: str
    seniority: str
    salary_min: Optional[float]
    salary_max: Optional[float]
    salary_currency: str
    salary_text: str
    experience_min: Optional[float]
    experience_max: Optional[float]
    also_on: list[AlsoOn]
    match: Optional[MatchOut]


class SourceStatusOut(BaseModel):
    name: str
    status: str
    count: int
    message: str


class SearchResponse(BaseModel):
    results: list[JobResult]
    total: int
    page: int
    page_size: int
    has_more: bool
    sources: list[SourceStatusOut]
    facets: dict[str, int]
    profile_used: bool = Field(description="True when match % was computed from the user's resume/profile")


def build_search_response(res: SearchResult) -> SearchResponse:
    """Shared by the Jobs search and the company jobs endpoints."""
    out = []
    for job, m in res.jobs:
        out.append(JobResult(
            id=job.uid, title=job.title, company=job.company, location=job.location,
            remote=job.remote, work_mode=job.work_mode, url=job.url,
            source=job.source, source_label=source_label(job.source), source_tier=source_priority(job.source),
            posted_at=job.posted_at, snippet=snippet(job.description),
            employment_type=job.employment_type, seniority=job.seniority,
            salary_min=job.salary_min, salary_max=job.salary_max,
            salary_currency=job.salary_currency, salary_text=job.salary_text,
            experience_min=job.experience_min, experience_max=job.experience_max,
            also_on=[AlsoOn(**a) for a in job.also_on],
            match=MatchOut(score=m.score, matched_skills=m.matched_skills, missing_skills=m.missing_skills) if m else None,
        ))
    return SearchResponse(
        results=out, total=res.total, page=res.page, page_size=res.page_size,
        has_more=res.page * res.page_size < res.total,
        sources=[SourceStatusOut(name=s.name, status=s.status, count=s.count, message=s.message) for s in res.sources],
        facets=res.facets, profile_used=res.profile_used,
    )


@router.get("/search", response_model=SearchResponse, dependencies=[Depends(require_feature("job_search"))])
async def search(
    q: str = Query("", max_length=120, description="Role / keywords"),
    location: str = Query("", max_length=120),
    country: str = Query("", max_length=2, description="ISO-2 country for aggregators (default from server)"),
    work_mode: str = Query("", pattern="^(|remote|hybrid|onsite)$"),
    salary_min: Optional[float] = Query(None, ge=0, description="Minimum annual salary, in salary_currency"),
    salary_currency: str = Query("", max_length=3),
    include_unspecified_salary: bool = True,
    experience_min: Optional[float] = Query(None, ge=0, le=40),
    experience_max: Optional[float] = Query(None, ge=0, le=40),
    employment_type: str = Query("", pattern="^(|full-time|part-time|contract|internship)$"),
    posted_within_days: Optional[int] = Query(None, ge=1, le=90),
    company: str = Query("", max_length=80),
    sources: list[str] = Query(default=[]),
    sort: str = Query("priority", pattern="^(priority|recent|match)$"),
    page: int = Query(1, ge=1, le=50),
    page_size: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    f = SearchFilters(
        q=q.strip(), location=location.strip(), country=country.strip().lower(), work_mode=work_mode,
        salary_min=salary_min, salary_currency=salary_currency.strip().upper(),
        include_unspecified_salary=include_unspecified_salary,
        experience_min=experience_min, experience_max=experience_max,
        employment_type=employment_type, posted_within_days=posted_within_days,
        company=company.strip(), sources=[s for s in sources if s], sort=sort,
    )
    profile = profile_view(await get_latest_profile(db, user), user)
    res = await search_jobs(f, profile, page=page, page_size=page_size)

    return build_search_response(res)


@router.get("/search/meta")
async def search_meta(user: User = Depends(get_current_user)):
    """Source keys + labels for the filter UI."""
    keys = ["career_page", "greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee",
            "linkedin", "naukri", "indeed", "glassdoor", "wellfound", "web", "other"]
    return {"sources": [{"key": k, "label": SOURCE_LABELS[k], "tier": source_priority(k)} for k in keys]}
