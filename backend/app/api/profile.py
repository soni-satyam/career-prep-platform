"""Candidate profile used for job-match %: upload / update a resume, edit skills."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.jobsearch.matching import CandidateProfileView
from app.jobsearch.text import (
    canonical_skill, dedupe_keep_order, estimate_experience_years, extract_skills, guess_title,
)
from app.models.profile import CandidateProfile
from app.models.user import User
from app.services.activity import log_activity
from app.services.documents import extract_text_from_upload

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileOut(BaseModel):
    has_profile: bool
    title: str = ""
    skills: list[str] = Field(default_factory=list)
    experience_years: Optional[float] = None
    source_filename: Optional[str] = None
    updated_at: Optional[datetime] = None


class ProfilePatch(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    skills: Optional[list[str]] = None
    experience_years: Optional[float] = Field(None, ge=0, le=60)


def _out(p: Optional[CandidateProfile]) -> ProfileOut:
    if p is None:
        return ProfileOut(has_profile=False)
    return ProfileOut(
        has_profile=bool(p.skills or p.title or p.experience_years is not None),
        title=p.title or "",
        skills=list(p.skills or []),
        experience_years=p.experience_years,
        source_filename=p.source_filename,
        updated_at=p.updated_at,
    )


async def get_latest_profile(db: AsyncSession, user: User) -> Optional[CandidateProfile]:
    res = await db.execute(
        select(CandidateProfile).where(CandidateProfile.user_id == user.id)
        .order_by(CandidateProfile.updated_at.desc()).limit(1)
    )
    return res.scalar_one_or_none()


def profile_view(p: Optional[CandidateProfile], user: User) -> Optional[CandidateProfileView]:
    """What the matcher sees. Falls back to the account's 'current role' when the resume has no title."""
    if p is None:
        return None
    view = CandidateProfileView(
        skills=list(p.skills or []),
        title=(p.title or user.current_role or "").strip(),
        experience_years=p.experience_years,
    )
    return view if view.usable else None


@router.get("", response_model=ProfileOut)
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return _out(await get_latest_profile(db, user))


@router.post("/resume", response_model=ProfileOut)
async def upload_resume(
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a PDF / DOCX / TXT resume (or paste text). Skills, title and years are extracted
    locally (no LLM call), so this is instant and costs no API quota."""
    if file is not None and file.filename:
        raw = await extract_text_from_upload(file)
        filename = file.filename
    elif text and text.strip():
        raw, filename = text.strip(), "pasted text"
    else:
        raise HTTPException(400, "Upload a resume file or paste its text.")
    if len(raw) < 30:
        raise HTTPException(400, "That resume looks too short to read.")

    skills = extract_skills(raw)
    p = await get_latest_profile(db, user)
    if p is None:
        p = CandidateProfile(user_id=user.id)
        db.add(p)
    p.raw_resume_text = raw[:60000]
    p.skills = skills
    p.experience_years = estimate_experience_years(raw)
    p.title = guess_title(raw) or user.current_role or None
    p.source_filename = filename[:500]
    p.structured = {"extracted_by": "rules", "skill_count": len(skills)}
    await db.flush()
    await db.refresh(p)
    await log_activity(db, user.id, "resume_uploaded", "Resume uploaded" if filename == "pasted text" else f"Resume uploaded: {filename}", f"{len(skills)} skills found", "/jobs")
    return _out(p)


@router.patch("", response_model=ProfileOut)
async def patch_profile(body: ProfilePatch, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = await get_latest_profile(db, user)
    if p is None:
        p = CandidateProfile(user_id=user.id)
        db.add(p)
    if body.title is not None:
        p.title = body.title.strip() or None
    if body.skills is not None:
        p.skills = dedupe_keep_order(canonical_skill(s) for s in body.skills if s.strip())[:80]
    if body.experience_years is not None:
        p.experience_years = body.experience_years
    await db.flush()
    await db.refresh(p)
    return _out(p)


@router.delete("", response_model=ProfileOut)
async def delete_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = await get_latest_profile(db, user)
    if p is not None:
        await db.delete(p)
        await db.flush()
    return ProfileOut(has_profile=False)
