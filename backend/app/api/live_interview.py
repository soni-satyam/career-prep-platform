"""Live AI interview API — start, answer, finish."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.live_interview_agent import (
    evaluate_and_continue,
    generate_final_report,
    start_interview,
)
from app.core.errors import llm_http_error
from app.api.deps import get_current_user
from app.api.feature_guard import require_feature
from app.core.database import get_db
from app.models.session import PreparationSession
from app.models.user import User

router = APIRouter(prefix="/live-interview", tags=["live-interview"])


class StartRequest(BaseModel):
    role: str = Field(..., min_length=2, max_length=120)
    difficulty: str = Field(default="medium")  # easy | medium | hard
    duration_minutes: int = Field(default=15, ge=5, le=60)
    resume_context: Optional[str] = None
    jd_context: Optional[str] = None


class StartResponse(BaseModel):
    interview_id: str
    role: str
    difficulty: str
    duration_minutes: int
    max_questions: int
    question: dict[str, Any]


class AnswerRequest(BaseModel):
    interview_id: str
    question_id: str
    question: str
    category: str = "technical"
    answer: str = Field(..., min_length=1)
    history: list[dict[str, Any]] = Field(default_factory=list)
    questions_asked: int = 1
    role: str = "Software Engineer"
    difficulty: str = "medium"
    max_questions: int = 6


class FinishRequest(BaseModel):
    interview_id: str
    role: str
    difficulty: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    save_session: bool = True


def _max_questions_for_duration(minutes: int) -> int:
    # ~2.5 min per question including answer + feedback
    return max(3, min(12, minutes // 3))


@router.post("/start", response_model=StartResponse)
async def api_start(
    body: StartRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_feature("interview_prep")),
):
    try:
        q = await start_interview(
            role=body.role,
            difficulty=body.difficulty,
            duration_minutes=body.duration_minutes,
            resume_context=body.resume_context or "",
            jd_context=body.jd_context or "",
        )
    except ValueError as e:
        status, detail = llm_http_error(e)
        raise HTTPException(status_code=status, detail=detail)
    except Exception as e:
        status, detail = llm_http_error(e)
        raise HTTPException(status_code=status, detail=detail)

    import uuid

    interview_id = uuid.uuid4().hex[:12]
    max_q = _max_questions_for_duration(body.duration_minutes)
    return StartResponse(
        interview_id=interview_id,
        role=body.role,
        difficulty=body.difficulty,
        duration_minutes=body.duration_minutes,
        max_questions=max_q,
        question={
            "question_id": q.get("question_id") or "q1",
            "category": q.get("category") or "technical",
            "question": q.get("question") or "Tell me about yourself.",
            "hints_for_evaluator": q.get("hints_for_evaluator"),
        },
    )


@router.post("/answer")
async def api_answer(
    body: AnswerRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_feature("interview_prep")),
):
    history = list(body.history)
    history.append(
        {
            "question_id": body.question_id,
            "question": body.question,
            "category": body.category,
            "answer": body.answer,
        }
    )
    try:
        result = await evaluate_and_continue(
            role=body.role,
            difficulty=body.difficulty,
            history=history,
            latest_answer=body.answer,
            questions_asked=body.questions_asked,
            max_questions=body.max_questions,
        )
    except ValueError as e:
        status, detail = llm_http_error(e)
        raise HTTPException(status_code=status, detail=detail)
    except Exception as e:
        status, detail = llm_http_error(e)
        raise HTTPException(status_code=status, detail=detail)

    evaluation = result.get("evaluation") or {}
    # attach eval onto last turn for client history
    return {
        "evaluation": evaluation,
        "done": bool(result.get("done")),
        "next_question": result.get("next_question"),
    }


@router.post("/finish")
async def api_finish(
    body: FinishRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_feature("interview_prep")),
):
    try:
        report = await generate_final_report(
            role=body.role,
            difficulty=body.difficulty,
            history=body.history,
        )
    except ValueError as e:
        status, detail = llm_http_error(e)
        raise HTTPException(status_code=status, detail=detail)
    except Exception as e:
        status, detail = llm_http_error(e)
        raise HTTPException(status_code=status, detail=detail)

    session_id = None
    if body.save_session:
        session = PreparationSession(
            user_id=current_user.id,
            title=f"Mock Interview — {body.role}"[:255],
            status="completed",
            progress_pct=100.0,
            interview_pack={
                "type": "live_interview",
                "role": body.role,
                "difficulty": body.difficulty,
                "history": body.history,
                "report": report,
            },
            plan={"meta": {"source": "live_interview"}, "report": report},
        )
        db.add(session)
        await db.flush()
        await db.refresh(session)
        session_id = session.id

    return {"report": report, "session_id": session_id}
