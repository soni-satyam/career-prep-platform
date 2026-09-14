"""Preparation APIs — full pipeline + individual agent endpoints."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import (
    analyze_gaps,
    analyze_jd,
    extract_profile,
    generate_interview_pack,
    generate_tailored_resume,
    run_full_pipeline,
)
from app.core.errors import llm_http_error
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.session import PreparationSession
from app.models.user import User
from app.rag.store import ingest_text
from app.services.export_resume import tailored_resume_to_html
from app.api.feature_guard import require_feature
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/prep", tags=["preparation"])


# ---------- Schemas ----------

class JDRequest(BaseModel):
    jd_text: str = Field(..., min_length=30)


class ProfileRequest(BaseModel):
    resume_text: str = Field(..., min_length=30)


class GapRequest(BaseModel):
    jd_analysis: dict[str, Any]
    profile: dict[str, Any]


class ResumeRequest(BaseModel):
    jd_analysis: dict[str, Any]
    profile: dict[str, Any]
    edit_instruction: Optional[str] = None


class InterviewRequest(BaseModel):
    jd_analysis: dict[str, Any]
    profile: dict[str, Any]
    tailored_resume: Optional[dict[str, Any]] = None
    num_questions: int = 8


class FullPipelineRequest(BaseModel):
    title: Optional[str] = None
    jd_text: str = Field(..., min_length=50)
    resume_text: Optional[str] = None
    target_role: Optional[str] = None
    company: Optional[str] = None


class SessionOut(BaseModel):
    id: int
    title: Optional[str]
    status: str
    progress_pct: float
    plan: Optional[dict[str, Any]] = None
    gap_analysis: Optional[dict[str, Any]] = None
    tailored_resume: Optional[dict[str, Any]] = None
    interview_pack: Optional[dict[str, Any]] = None

    class Config:
        from_attributes = True


def _llm_error(e: Exception) -> HTTPException:
    status, detail = llm_http_error(e)
    return HTTPException(status_code=status, detail=detail)



# ---------- Individual agent endpoints ----------

@router.post("/analyze-jd")
async def api_analyze_jd(
    body: JDRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        return await analyze_jd(body.jd_text)
    except Exception as e:
        raise _llm_error(e)


@router.post("/extract-profile")
async def api_extract_profile(
    body: ProfileRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        return await extract_profile(body.resume_text)
    except Exception as e:
        raise _llm_error(e)


@router.post("/analyze-gaps")
async def api_analyze_gaps(
    body: GapRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        return await analyze_gaps(body.jd_analysis, body.profile)
    except Exception as e:
        raise _llm_error(e)


@router.post("/tailor-resume")
async def api_tailor_resume(
    body: ResumeRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        return await generate_tailored_resume(
            body.jd_analysis, body.profile, body.edit_instruction or ""
        )
    except Exception as e:
        raise _llm_error(e)


@router.post("/interview-pack")
async def api_interview_pack(
    body: InterviewRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        return await generate_interview_pack(
            body.jd_analysis,
            body.profile,
            body.tailored_resume,
            body.num_questions,
        )
    except Exception as e:
        raise _llm_error(e)


# ---------- Full pipeline → session ----------

@router.post("/sessions", response_model=SessionOut, status_code=201)
async def create_session(
    body: FullPipelineRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run the full multi-agent pipeline and persist a preparation session."""
    try:
        pipeline = await run_full_pipeline(
            jd_text=body.jd_text,
            resume_text=body.resume_text or "",
            target_role=body.target_role or "",
            company=body.company or "",
        )
    except Exception as e:
        raise _llm_error(e)

    title = body.title
    if not title:
        role = body.target_role or (pipeline.get("jd_analysis") or {}).get("title") or "Preparation Plan"
        company = body.company or ""
        title = f"{role}" + (f" @ {company}" if company else "")

    session = PreparationSession(
        user_id=current_user.id,
        title=title[:255],
        status="active",
        progress_pct=25.0,
        plan={
            "preparation_plan": pipeline.get("preparation_plan", []),
            "estimated_weeks": pipeline.get("estimated_weeks", 4),
            "jd_analysis": pipeline.get("jd_analysis"),
            "profile": pipeline.get("profile"),
            "resume_tips": pipeline.get("resume_tips", []),
            "meta": pipeline.get("meta"),
        },
        gap_analysis=pipeline.get("gap_analysis"),
        tailored_resume=pipeline.get("tailored_resume"),
        interview_pack=pipeline.get("interview_pack"),
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    # RAG: ingest JD + resume chunks for this session
    try:
        if body.jd_text:
            await ingest_text(
                db,
                user_id=current_user.id,
                text_content=body.jd_text,
                source_type="jd",
                session_id=session.id,
            )
        if body.resume_text:
            await ingest_text(
                db,
                user_id=current_user.id,
                text_content=body.resume_text,
                source_type="resume",
                session_id=session.id,
            )
    except Exception:
        pass  # non-fatal if embeddings unavailable

    return session


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(PreparationSession, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Not found")
    return session


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PreparationSession)
        .where(PreparationSession.user_id == current_user.id)
        .order_by(PreparationSession.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()




@router.get("/sessions/{session_id}/export-html", response_class=HTMLResponse)
async def export_session_resume_html(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download tailored resume as printable HTML (use browser Print → PDF)."""
    session = await db.get(PreparationSession, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Not found")
    resume = session.tailored_resume
    if not resume:
        raise HTTPException(400, "No tailored resume on this session")
    html = tailored_resume_to_html(resume, title=session.title or "Resume")
    return HTMLResponse(
        content=html,
        headers={
            "Content-Disposition": f'inline; filename="resume-{session_id}.html"'
        },
    )

# ---------- File upload (resume PDF / DOCX / TXT) ----------

from fastapi import File, UploadFile
from app.services.documents import extract_text_from_upload


@router.post("/extract-text")
async def extract_resume_text(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Extract plain text from an uploaded resume (PDF, DOCX, TXT)."""
    text = await extract_text_from_upload(file)
    return {"filename": file.filename, "text": text, "length": len(text)}
