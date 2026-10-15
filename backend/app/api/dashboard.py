"""GET /api/v1/dashboard - everything the home screen needs in one request,
plus /dashboard/recommended (slower: calls the job sources, so it loads separately)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.job_search import AlsoOn, JobResult, MatchOut
from app.api.profile import get_latest_profile, profile_view
from app.api.tracker import ApplicationOut, SavedJobOut
from app.core.database import get_db
from app.jobsearch.posting import SearchFilters, source_label, source_priority
from app.jobsearch.service import search_jobs
from app.jobsearch.text import snippet
from app.models.profile import CandidateProfile
from app.models.session import PreparationSession
from app.models.tracker import APPLICATION_STATUSES, ActivityEvent, JobApplication, SavedJob
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

STALE_RESUME_DAYS = 90
FOLLOW_UP_AFTER_DAYS = 10


# ------------------------------------------------------------------ schemas

class ResumeStatus(BaseModel):
    uploaded: bool
    filename: Optional[str] = None
    title: str = ""
    skills_count: int = 0
    experience_years: Optional[float] = None
    updated_at: Optional[datetime] = None
    age_days: Optional[int] = None
    stale: bool = False
    completeness: int = 0                 # 0-100
    next_steps: list[str] = []


class Stats(BaseModel):
    saved_jobs: int
    applications: int
    active: int                           # applied + interviewing
    interviewing: int
    offers: int
    rejected: int
    prep_sessions: int
    by_status: dict[str, int]


class ActivityItem(BaseModel):
    id: str
    type: str
    title: str
    subtitle: str
    link: str
    at: datetime


class DashboardOut(BaseModel):
    resume: ResumeStatus
    stats: Stats
    activity: list[ActivityItem]
    saved_jobs: list[SavedJobOut]
    applications: list[ApplicationOut]
    upcoming: list[ApplicationOut]        # applications with a next step coming up
    follow_up: list[ApplicationOut]       # applied a while ago, no movement


class RecommendedOut(BaseModel):
    jobs: list[JobResult]
    reason: str                           # ok | no_resume | no_results
    based_on: str = ""
    saved_ids: list[str] = []
    applied_ids: list[str] = []


def to_job_result(job, m) -> JobResult:
    return JobResult(
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
    )


# ------------------------------------------------------------------ helpers

def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def resume_status(p: Optional[CandidateProfile], now: Optional[datetime] = None) -> ResumeStatus:
    now = now or datetime.now(timezone.utc)
    if p is None or not (p.skills or p.title or p.experience_years is not None):
        return ResumeStatus(uploaded=False, next_steps=["Upload your resume to get job match % and recommendations."])
    skills = list(p.skills or [])
    updated = _aware(p.updated_at)
    age = (now - updated).days if updated else None
    stale = age is not None and age > STALE_RESUME_DAYS

    score, steps = 0, []
    score += 35 if p.raw_resume_text else 10
    if len(skills) >= 8:
        score += 25
    elif skills:
        score += 12
        steps.append("Add more skills: we found only %d, and 8+ gives better matches." % len(skills))
    else:
        steps.append("No skills were detected. Add them under Edit on the Jobs page.")
    if p.experience_years is not None:
        score += 15
    else:
        steps.append("Add your years of experience so we can check experience fit.")
    if p.title:
        score += 15
    else:
        steps.append("Add your current role so matches can compare job titles.")
    score += 10 if not stale else 0
    if stale:
        steps.append(f"Your resume is {age} days old. Re-upload it if anything has changed.")
    return ResumeStatus(
        uploaded=True, filename=p.source_filename, title=p.title or "", skills_count=len(skills),
        experience_years=p.experience_years, updated_at=updated, age_days=age, stale=stale,
        completeness=min(100, score), next_steps=steps,
    )


_SENIORITY = re.compile(r"\b(senior|sr|junior|jr|lead|staff|principal|associate|intern)\b\.?", re.I)


def recommendation_query(title: str) -> str:
    return " ".join(_SENIORITY.sub(" ", title or "").split())[:80]


# ----------------------------------------------------------------- endpoints

@router.get("", response_model=DashboardOut)
async def dashboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    today = now.date()

    profile = await get_latest_profile(db, user)

    counts = dict((await db.execute(
        select(JobApplication.status, func.count()).where(JobApplication.user_id == user.id).group_by(JobApplication.status)
    )).all())
    by_status = {s: int(counts.get(s, 0)) for s in APPLICATION_STATUSES}
    saved_count = (await db.execute(select(func.count()).select_from(SavedJob).where(SavedJob.user_id == user.id))).scalar_one()
    sessions_rows = (await db.execute(
        select(PreparationSession).where(PreparationSession.user_id == user.id).order_by(PreparationSession.created_at.desc()).limit(8)
    )).scalars().all()
    sessions_count = (await db.execute(select(func.count()).select_from(PreparationSession).where(PreparationSession.user_id == user.id))).scalar_one()

    stats = Stats(
        saved_jobs=int(saved_count), applications=sum(by_status.values()),
        active=by_status["applied"] + by_status["interviewing"], interviewing=by_status["interviewing"],
        offers=by_status["offer"], rejected=by_status["rejected"], prep_sessions=int(sessions_count), by_status=by_status,
    )

    saved = (await db.execute(
        select(SavedJob).where(SavedJob.user_id == user.id).order_by(SavedJob.created_at.desc(), SavedJob.id.desc()).limit(6)
    )).scalars().all()
    apps = (await db.execute(
        select(JobApplication).where(JobApplication.user_id == user.id).order_by(JobApplication.updated_at.desc(), JobApplication.id.desc()).limit(50)
    )).scalars().all()

    upcoming = sorted(
        [a for a in apps if a.next_step_date and a.next_step_date >= today and a.status in ("applied", "interviewing", "offer")],
        key=lambda a: a.next_step_date,
    )[:5]
    cutoff = now - timedelta(days=FOLLOW_UP_AFTER_DAYS)
    follow_up = [a for a in apps if a.status == "applied" and (_aware(a.updated_at) or now) < cutoff and not a.next_step_date][:5]

    events = (await db.execute(
        select(ActivityEvent).where(ActivityEvent.user_id == user.id).order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc()).limit(15)
    )).scalars().all()
    feed = [ActivityItem(id=f"e{e.id}", type=e.type, title=e.title, subtitle=e.subtitle, link=e.link, at=_aware(e.created_at) or now) for e in events]
    for s in sessions_rows:       # prep sessions are shown in the feed without touching that feature's code
        feed.append(ActivityItem(
            id=f"s{s.id}", type="session", title=s.title or f"Prep session #{s.id}",
            subtitle=f"{(s.status or '').title()} · {int(s.progress_pct or 0)}% complete",
            link=f"/sessions/{s.id}", at=_aware(s.created_at) or now,
        ))
    feed.sort(key=lambda i: i.at, reverse=True)

    return DashboardOut(
        resume=resume_status(profile, now), stats=stats, activity=feed[:10],
        saved_jobs=[SavedJobOut.model_validate(x) for x in saved],
        applications=[ApplicationOut.model_validate(x) for x in apps[:12]],
        upcoming=[ApplicationOut.model_validate(x) for x in upcoming],
        follow_up=[ApplicationOut.model_validate(x) for x in follow_up],
    )


@router.get("/recommended", response_model=RecommendedOut)
async def recommended(limit: int = Query(6, ge=1, le=12), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Best-matching open jobs for this user's resume. Needs a resume (match % is the whole point)."""
    profile = profile_view(await get_latest_profile(db, user), user)
    saved = list((await db.execute(select(SavedJob.job_uid).where(SavedJob.user_id == user.id))).scalars().all())
    applied = list((await db.execute(select(JobApplication.job_uid).where(JobApplication.user_id == user.id, JobApplication.job_uid.is_not(None)))).scalars().all())
    if profile is None:
        return RecommendedOut(jobs=[], reason="no_resume", saved_ids=saved, applied_ids=applied)

    query = recommendation_query(profile.title)
    based_on = query or "your skills"
    res = await search_jobs(SearchFilters(q=query, sort="match", posted_within_days=45), profile, page_size=limit * 3)
    if not res.jobs and query:               # narrow title found nothing: broaden to everything, still ranked by match
        res = await search_jobs(SearchFilters(sort="match"), profile, page_size=limit * 3)
        based_on = "your skills"
    done = set(applied)
    picks = [(j, m) for j, m in res.jobs if j.uid not in done and m is not None and m.score >= 35][:limit]
    return RecommendedOut(
        jobs=[to_job_result(j, m) for j, m in picks], reason="ok" if picks else "no_results",
        based_on=based_on, saved_ids=saved, applied_ids=applied,
    )
