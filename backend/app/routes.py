"""PART 7e - HTTP endpoints. Thin on purpose: validate -> store -> call services."""
import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app import config, db, services
from app.agents.input_validator import input_validator_node
from app.api_models import (
    GraphInfo, PracticeRequest, PracticeResult, SessionCreated, SessionOut,
)
from app.graph import career_graph
from app.ratelimit import limit_practice, limit_sessions
from app.tools.resume_parser import parse_resume

log = logging.getLogger("career_prep")
router = APIRouter(prefix="/api")
TERMINAL_EVENTS = {"done", "failed", "rejected"}


def _get_or_404(session_id: str, private: bool = False) -> dict:
    s = db.get_session(session_id, private=private)
    if not s:
        raise HTTPException(404, "Session not found (it may have expired).")
    return s


# ---------------------------------------------------------------- create
@router.post("/sessions", response_model=SessionCreated, status_code=202,
             dependencies=[Depends(limit_sessions)])
async def create_session(
    job_description: str = Form(...),
    company_name: str = Form(...),
    resume_text: str | None = Form(None),
    resume_file: UploadFile | None = File(None),
):
    """Start a prep run. Returns immediately; follow progress via /events, fetch result via GET."""
    if not config.llm_ready():
        raise HTTPException(503, "Server has no LLM API key configured.")
    if len(job_description) > config.MAX_JD_INPUT_CHARS:
        raise HTTPException(413, "Job description is too long.")
    if len(company_name) > config.MAX_COMPANY_CHARS:
        raise HTTPException(422, "Company name is too long.")

    if resume_file is not None and resume_file.filename:
        limit = config.MAX_RESUME_FILE_MB * 1024 * 1024
        data = await resume_file.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(413, f"Resume file exceeds {config.MAX_RESUME_FILE_MB} MB.")
        try:
            text = await asyncio.to_thread(parse_resume, resume_file.filename, data)
        except ValueError as e:
            raise HTTPException(422, str(e))
        except Exception:
            raise HTTPException(422, "Could not read this file. Is it a valid PDF/DOCX?")
    elif resume_text:
        text = resume_text
    else:
        raise HTTPException(422, "Provide resume_file or resume_text.")

    # Fail fast with the same validator the graph uses (no LLM spent on bad input).
    checked = input_validator_node(
        {"resume_text": text, "job_description": job_description, "company_name": company_name})
    if not checked["is_valid"]:
        raise HTTPException(422, checked["validation_error"])

    session_id = uuid.uuid4().hex
    await asyncio.to_thread(
        db.create_session, session_id, checked["company_name"],
        checked["job_description"], checked["resume_text"])
    services.spawn(services.run_prep_session(session_id))
    return SessionCreated(session_id=session_id, status="pending")


# ---------------------------------------------------------------- read
@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: str):
    return _get_or_404(session_id)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str):
    """Deletes the resume, report and practice history for this session."""
    if not db.delete_session(session_id):
        raise HTTPException(404, "Session not found.")


# ---------------------------------------------------------------- progress (SSE)
@router.get("/sessions/{session_id}/events")
async def stream_events(session_id: str, request: Request):
    """Server-Sent Events. Each finished graph node is one event; stream ends on done/failed/rejected.
    Reconnecting with the `Last-Event-ID` header resumes where you left off."""
    if await asyncio.to_thread(db.get_status, session_id) is None:
        raise HTTPException(404, "Session not found.")
    try:
        last_id = int(request.headers.get("last-event-id", "0"))
    except ValueError:
        last_id = 0

    async def generator():
        nonlocal last_id
        idle = 0.0
        while not await request.is_disconnected():
            events = await asyncio.to_thread(db.get_events_after, session_id, last_id)
            finished = False
            for e in events:
                last_id = e["id"]
                payload = {k: e[k] for k in ("type", "node", "message", "data", "created_at")}
                yield f"id: {e['id']}\nevent: {e['type']}\ndata: {json.dumps(payload)}\n\n"
                finished = finished or e["type"] in TERMINAL_EVENTS
            if finished:
                return
            if not events:
                status = await asyncio.to_thread(db.get_status, session_id)
                if status is None or status in db.TERMINAL_STATUSES:
                    return
                idle += 0.4
                if idle >= 15:
                    yield ": keep-alive\n\n"
                    idle = 0.0
            else:
                idle = 0.0
            await asyncio.sleep(0.4)

    return StreamingResponse(
        generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- practice
def _find_question(report: dict, question_id: str) -> dict | None:
    for qs in report["questions_by_category"].values():
        for q in qs:
            if q["id"] == question_id:
                return q
    return None


@router.post("/sessions/{session_id}/practice", response_model=PracticeResult,
             dependencies=[Depends(limit_practice)])
async def practice(session_id: str, body: PracticeRequest):
    """Score a practice answer and get a follow-up question (mock-interview graph)."""
    if not config.llm_ready():
        raise HTTPException(503, "Server has no LLM API key configured.")
    session = await asyncio.to_thread(_get_or_404, session_id, True)
    if session["status"] != "completed":
        raise HTTPException(409, "Prep for this session isn't finished yet.")
    q = _find_question(session["report"], body.question_id)
    if not q:
        raise HTTPException(404, f"Unknown question_id '{body.question_id}'.")
    question_text = body.follow_up_question or q["question"]

    try:
        out = await services.run_practice(session, question_text, body.answer)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Evaluation timed out. Please try again.")
    except Exception as exc:
        log.exception("practice failed for %s", session_id)
        raise HTTPException(502, services.friendly_error(exc))

    if out.get("eval_error"):
        raise HTTPException(422, out["eval_error"])

    attempt_id, created = await asyncio.to_thread(
        db.add_attempt, session_id, body.question_id, question_text, body.answer,
        out["feedback"].model_dump(), out["follow_up"].model_dump())
    return PracticeResult(
        attempt_id=attempt_id, question_id=body.question_id, question=question_text,
        answer=body.answer, feedback=out["feedback"], follow_up=out["follow_up"], created_at=created)


@router.get("/sessions/{session_id}/practice", response_model=list[PracticeResult])
def practice_history(session_id: str):
    _get_or_404(session_id)
    return db.get_attempts(session_id)


# ---------------------------------------------------------------- meta
@router.get("/graph", response_model=GraphInfo)
def graph_info():
    """Node/edge list so a frontend can draw a live progress diagram."""
    g = career_graph.get_graph()
    return GraphInfo(
        nodes=[n for n in g.nodes if not n.startswith("__")],
        edges=[(e.source, e.target, bool(e.conditional)) for e in g.edges],
    )
