"""Preparation APIs — full pipeline + individual agent endpoints."""

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
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
from app.core.config import get_settings
from app.core.errors import llm_http_error
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.session import PreparationSession
from app.models.user import User
from app.rag.store import ingest_text
from app.agents.contracts import TailoredResume
from app.services.ats_score import compare as ats_compare, rescore as ats_rescore, unverified_skills
from app.services.readiness import verdict as readiness_verdict
from app.services.resume_validation import validate_docx, validate_pdf
from app.services.export_resume_docx import render_resume_docx
from app.services.export_resume import tailored_resume_to_html
from app.services.export_resume_pdf import DEFAULT_TEMPLATE, TEMPLATES, render_resume_pdf
from app.api.feature_guard import require_feature
from fastapi.responses import HTMLResponse, Response

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
    # full = every agent (default). resume / interview skip the agents that page
    # never displays, saving 1-3 LLM calls per run. See orchestrator.PIPELINE_MODES.
    mode: Literal["full", "resume", "interview"] = "full"


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

    @field_validator("plan", mode="after")
    @classmethod
    def _hide_private(cls, v):
        # original_resume_text is stored only so edits can be re-checked server-side
        return {k: x for k, x in v.items() if k != "original_resume_text"} if isinstance(v, dict) else v


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
            mode=body.mode,
        )
    except Exception as e:
        raise _llm_error(e)

    title = body.title
    if not title:
        role = body.target_role or (pipeline.get("jd_analysis") or {}).get("title") or "Preparation Plan"
        company = body.company or ""
        title = f"{role}" + (f" @ {company}" if company else "")

    # Before/after keyword match against the JD (same terms for both, so the numbers are comparable).
    try:
        ats_match = ats_compare(
            body.resume_text, pipeline.get("tailored_resume"), pipeline.get("jd_analysis"), body.jd_text
        )
    except Exception:
        ats_match = None  # the meter is a nice-to-have; never fail the session over it
    try:
        unverified = unverified_skills(body.resume_text, pipeline.get("tailored_resume") or {})
        readiness = readiness_verdict(ats_match, pipeline.get("gap_analysis"))
    except Exception:
        unverified, readiness = [], None

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
            "ats_match": ats_match,
            "readiness": readiness,
            "unverified_skills": unverified,
            "original_resume_text": (body.resume_text or "")[:30000],
        },
        gap_analysis=pipeline.get("gap_analysis"),
        tailored_resume=pipeline.get("tailored_resume"),
        interview_pack=pipeline.get("interview_pack"),
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    # RAG: ingest JD + resume chunks for this session.
    # Nothing reads these vectors yet and every ingest costs embedding calls on the
    # Gemini key, so it is opt-in (RAG_INGEST_ENABLED=true) until retrieval is used.
    try:
        if get_settings().rag_ingest_enabled and body.jd_text:
            await ingest_text(
                db,
                user_id=current_user.id,
                text_content=body.jd_text,
                source_type="jd",
                session_id=session.id,
            )
        if get_settings().rag_ingest_enabled and body.resume_text:
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

@router.get("/resume-templates")
async def list_resume_templates(current_user: User = Depends(get_current_user)):
    return {
        "default": DEFAULT_TEMPLATE,
        "templates": [
            {"key": t.key, "label": t.label, "description": t.description, "style": asdict(t)} for t in TEMPLATES.values()
        ],
    }


@router.get("/sessions/{session_id}/export-pdf")
async def export_session_resume_pdf(
    session_id: int,
    template: Literal["ats_classic", "ats_compact", "ats_serif"] = DEFAULT_TEMPLATE,
    page: Literal["a4", "letter"] = "a4",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download the tailored resume as an ATS-friendly, text-based PDF."""
    session = await db.get(PreparationSession, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Not found")
    resume = session.tailored_resume
    if not resume:
        raise HTTPException(400, "No tailored resume on this session")
    pdf = render_resume_pdf(resume, template=template, page=page)
    name = re.sub(r"[^A-Za-z0-9]+", "_", str((resume.get("profile") or {}).get("name") or "Resume")).strip("_") or "Resume"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}_Resume.pdf"'},
    )



# ---------- Edit → approve → generate & validate files ----------

TemplateKey = Literal["ats_classic", "ats_compact", "ats_serif"]
PageKey = Literal["a4", "letter"]


async def _owned_session(db: AsyncSession, session_id: int, user: User) -> PreparationSession:
    session = await db.get(PreparationSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    return session


def _resume_filename(resume: dict[str, Any], ext: str) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "_", str((resume.get("profile") or {}).get("name") or "Resume")).strip("_") or "Resume"
    return f"{name}_Resume.{ext}"


@router.patch("/sessions/{session_id}/resume")
async def save_edited_resume(
    session_id: int,
    body: TailoredResume,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the user's edits, then re-score the match and readiness for the edited text."""
    session = await _owned_session(db, session_id, current_user)
    resume = body.model_dump()
    if len(json.dumps(resume)) > 200_000 or any(len(resume[k]) > 40 for k in ("experience", "projects", "education", "awards")):
        raise HTTPException(413, "Resume is too large")

    plan = dict(session.plan or {})
    match = plan.get("ats_match")
    if match:
        plan["ats_match"] = ats_rescore(match, resume)
    plan["unverified_skills"] = unverified_skills(plan.get("original_resume_text"), resume)
    plan["readiness"] = readiness_verdict(plan.get("ats_match"), session.gap_analysis)
    plan.pop("resume_approval", None)  # edited after approval -> must be approved again
    session.tailored_resume = resume
    session.plan = plan
    await db.flush()
    return {
        "tailored_resume": resume,
        "ats_match": plan.get("ats_match"),
        "readiness": plan.get("readiness"),
        "unverified_skills": plan["unverified_skills"],
    }


@router.post("/sessions/{session_id}/resume/approve")
async def approve_resume(
    session_id: int,
    template: TemplateKey = DEFAULT_TEMPLATE,
    page: PageKey = "a4",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate the PDF and DOCX from the saved resume, validate both, and return download links.

    Nothing is marked approved unless every check passes.
    """
    session = await _owned_session(db, session_id, current_user)
    resume = session.tailored_resume
    if not resume:
        raise HTTPException(400, "No tailored resume on this session")

    pdf = render_resume_pdf(resume, template=template, page=page)
    docx_bytes = render_resume_docx(resume, template=template, page=page)
    validation = {"pdf": validate_pdf(pdf, resume), "docx": validate_docx(docx_bytes, resume)}
    ok = validation["pdf"]["ok"] and validation["docx"]["ok"]

    base = f"/api/v1/prep/sessions/{session_id}"
    q = f"?template={template}&page={page}"
    files = [
        {"format": "pdf", "label": "PDF", "filename": _resume_filename(resume, "pdf"), "url": f"{base}/export-pdf{q}",
         "pages": validation["pdf"]["pages"], "size_kb": round(len(pdf) / 1024, 1)},
        {"format": "docx", "label": "Word (DOCX)", "filename": _resume_filename(resume, "docx"), "url": f"{base}/export-docx{q}",
         "pages": None, "size_kb": round(len(docx_bytes) / 1024, 1)},
    ] if ok else []

    approved_at = datetime.now(timezone.utc).isoformat()
    if ok:
        plan = dict(session.plan or {})
        plan["resume_approval"] = {"approved_at": approved_at, "template": template, "page": page}
        session.plan = plan
        await db.flush()
    return {"approved": ok, "approved_at": approved_at if ok else None, "template": template, "page": page,
            "validation": validation, "files": files}


@router.get("/sessions/{session_id}/export-docx")
async def export_session_resume_docx(
    session_id: int,
    template: TemplateKey = DEFAULT_TEMPLATE,
    page: PageKey = "a4",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, session_id, current_user)
    resume = session.tailored_resume
    if not resume:
        raise HTTPException(400, "No tailored resume on this session")
    return Response(
        content=render_resume_docx(resume, template=template, page=page),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{_resume_filename(resume, "docx")}"'},
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
