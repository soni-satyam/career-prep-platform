"""Saved jobs + application tracker."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.tracker import APPLICATION_STATUSES, JobApplication, SavedJob
from app.models.user import User
from app.services.activity import log_activity

router = APIRouter(prefix="/tracker", tags=["tracker"])

STATUS_LABEL = {"applied": "Applied", "interviewing": "Interviewing", "offer": "Offer", "rejected": "Rejected", "withdrawn": "Withdrawn"}


# ------------------------------------------------------------------ schemas

class SavedJobIn(BaseModel):
    job_uid: str = Field(min_length=4, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    company: str = Field("", max_length=255)
    location: str = Field("", max_length=255)
    url: str = Field("", max_length=2048)
    source: str = Field("", max_length=50)
    source_label: str = Field("", max_length=80)
    posted_at: Optional[datetime] = None
    salary_text: str = Field("", max_length=120)
    match_score: Optional[float] = Field(None, ge=0, le=100)


class SavedJobOut(BaseModel):
    id: int
    job_uid: str
    title: str
    company: str
    location: str
    url: str
    source: str
    source_label: str
    posted_at: Optional[datetime]
    salary_text: str
    match_score: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


class ApplicationIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    company: str = Field("", max_length=255)
    location: str = Field("", max_length=255)
    url: str = Field("", max_length=2048)
    source_label: str = Field("", max_length=80)
    job_uid: Optional[str] = Field(None, max_length=64)
    status: str = "applied"
    applied_on: Optional[date] = None
    next_step: str = Field("", max_length=255)
    next_step_date: Optional[date] = None
    notes: str = Field("", max_length=4000)


class ApplicationPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    company: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = None
    applied_on: Optional[date] = None
    next_step: Optional[str] = Field(None, max_length=255)
    next_step_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=4000)
    clear_next_step_date: bool = False


class ApplicationOut(BaseModel):
    id: int
    job_uid: Optional[str]
    title: str
    company: str
    location: str
    url: str
    source_label: str
    status: str
    applied_on: Optional[date]
    next_step: str
    next_step_date: Optional[date]
    notes: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


def _check_status(s: str) -> str:
    if s not in APPLICATION_STATUSES:
        raise HTTPException(422, f"status must be one of: {', '.join(APPLICATION_STATUSES)}")
    return s


# -------------------------------------------------------------- saved jobs

@router.get("/saved", response_model=list[SavedJobOut])
async def list_saved(limit: int = Query(100, ge=1, le=300), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SavedJob).where(SavedJob.user_id == user.id).order_by(SavedJob.created_at.desc(), SavedJob.id.desc()).limit(limit))
    return res.scalars().all()


@router.get("/saved/ids")
async def saved_ids(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """job_uids the user has saved or applied to - lets job cards show their state in one request."""
    saved = (await db.execute(select(SavedJob.job_uid).where(SavedJob.user_id == user.id))).scalars().all()
    applied = (await db.execute(select(JobApplication.job_uid).where(JobApplication.user_id == user.id, JobApplication.job_uid.is_not(None)))).scalars().all()
    return {"saved": list(saved), "applied": list(applied)}


@router.post("/saved", response_model=SavedJobOut, status_code=201)
async def save_job(body: SavedJobIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_uid == body.job_uid))
    row = res.scalar_one_or_none()
    if row is not None:                    # idempotent: saving twice is fine
        return row
    row = SavedJob(user_id=user.id, **body.model_dump())
    db.add(row)
    await db.flush()
    await db.refresh(row)
    await log_activity(db, user.id, "job_saved", f"Saved {body.title}", body.company, "/home")
    return row


@router.delete("/saved/{job_uid}")
async def unsave_job(job_uid: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_uid == job_uid))
    return {"ok": True}


# ------------------------------------------------------------ applications

@router.get("/applications", response_model=list[ApplicationOut])
async def list_applications(
    status: str = Query("", description="filter by status"),
    limit: int = Query(200, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(JobApplication).where(JobApplication.user_id == user.id)
    if status:
        stmt = stmt.where(JobApplication.status == _check_status(status))
    res = await db.execute(stmt.order_by(JobApplication.updated_at.desc(), JobApplication.id.desc()).limit(limit))
    return res.scalars().all()


@router.post("/applications", response_model=ApplicationOut, status_code=201)
async def add_application(body: ApplicationIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    data = body.model_dump()
    _check_status(data["status"])
    if data["applied_on"] is None and data["status"] != "withdrawn":
        data["applied_on"] = datetime.now(timezone.utc).date()
    if data["job_uid"]:                    # one application per job
        existing = (await db.execute(select(JobApplication).where(JobApplication.user_id == user.id, JobApplication.job_uid == data["job_uid"]))).scalar_one_or_none()
        if existing is not None:
            return existing
    row = JobApplication(user_id=user.id, **data)
    db.add(row)
    await db.flush()
    await db.refresh(row)
    await log_activity(db, user.id, "application_added", f"Applied to {row.title}", row.company, "/home")
    return row


@router.patch("/applications/{app_id}", response_model=ApplicationOut)
async def update_application(app_id: int, body: ApplicationPatch, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await db.get(JobApplication, app_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Application not found")
    old_status = row.status
    patch = body.model_dump(exclude_unset=True)
    clear = patch.pop("clear_next_step_date", False)
    if "status" in patch and patch["status"] is not None:
        _check_status(patch["status"])
    for k, v in patch.items():
        if v is not None:
            setattr(row, k, v)
    if clear:
        row.next_step_date = None
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(row)
    if row.status != old_status:
        await log_activity(db, user.id, "application_status", f"{row.title}: {STATUS_LABEL.get(row.status, row.status)}", row.company, "/home")
    return row


@router.delete("/applications/{app_id}")
async def delete_application(app_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await db.get(JobApplication, app_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Application not found")
    await db.delete(row)
    return {"ok": True}
