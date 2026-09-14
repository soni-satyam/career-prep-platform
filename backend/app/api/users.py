"""User profile / settings endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = None
    current_role: Optional[str] = None
    location: Optional[str] = None


class UserOut(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    bio: Optional[str]
    current_role: Optional[str]
    location: Optional[str]
    is_superuser: bool = False
    oauth_provider: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.full_name is not None:
        current_user.full_name = body.full_name
    if body.bio is not None:
        current_user.bio = body.bio
    if body.current_role is not None:
        current_user.current_role = body.current_role
    if body.location is not None:
        current_user.location = body.location
    await db.flush()
    await db.refresh(current_user)
    return current_user
