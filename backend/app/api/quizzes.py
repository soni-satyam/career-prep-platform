"""Practice quizzes API."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.quiz_agent import generate_quiz
from app.core.errors import llm_http_error
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


class QuizRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=200)
    difficulty: str = Field(default="medium")  # easy | medium | hard
    num_questions: int = Field(default=5, ge=3, le=15)
    context: Optional[str] = None


@router.post("/generate")
async def create_quiz(
    body: QuizRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        return await generate_quiz(
            topic=body.topic,
            difficulty=body.difficulty,
            num_questions=body.num_questions,
            context=body.context or "",
        )
    except ValueError as e:
        status, detail = llm_http_error(e)
        raise HTTPException(status_code=status, detail=detail)
    except Exception as e:
        status, detail = llm_http_error(e)
        raise HTTPException(status_code=status, detail=detail)
