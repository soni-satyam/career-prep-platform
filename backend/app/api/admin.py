"""Admin endpoints — manage users and feature flags."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.feature import FeatureFlag
from app.models.session import PreparationSession
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


# ---------- Schemas ----------

class UserAdminOut(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    is_active: bool
    is_superuser: bool
    oauth_provider: Optional[str]
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FeatureOut(BaseModel):
    id: int
    key: str
    name: str
    description: Optional[str]
    enabled: bool

    class Config:
        from_attributes = True


class FeatureUpdate(BaseModel):
    enabled: bool


class StatsOut(BaseModel):
    total_users: int
    total_sessions: int
    active_features: int


# ---------- Stats ----------

@router.get("/stats", response_model=StatsOut)
async def stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    users = await db.scalar(select(func.count()).select_from(User))
    sessions = await db.scalar(select(func.count()).select_from(PreparationSession))
    features = await db.scalar(
        select(func.count()).select_from(FeatureFlag).where(FeatureFlag.enabled == True)
    )
    return StatsOut(
        total_users=users or 0,
        total_sessions=sessions or 0,
        active_features=features or 0,
    )


# ---------- Users ----------

@router.get("/users", response_model=List[UserAdminOut])
async def list_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.id.desc()).limit(200))
    return result.scalars().all()


@router.patch("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == admin.id:
        raise HTTPException(400, "Cannot deactivate yourself")
    user.is_active = not user.is_active
    await db.flush()
    return {"id": user.id, "is_active": user.is_active}


@router.patch("/users/{user_id}/toggle-admin")
async def toggle_user_admin(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == admin.id:
        raise HTTPException(400, "Cannot change your own admin status")
    user.is_superuser = not user.is_superuser
    await db.flush()
    return {"id": user.id, "is_superuser": user.is_superuser}


# ---------- Feature Flags ----------

@router.get("/features", response_model=List[FeatureOut])
async def list_features(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(FeatureFlag).order_by(FeatureFlag.key))
    return result.scalars().all()


@router.patch("/features/{key}", response_model=FeatureOut)
async def update_feature(
    key: str,
    body: FeatureUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(FeatureFlag).where(FeatureFlag.key == key))
    feature = result.scalar_one_or_none()
    if not feature:
        raise HTTPException(404, "Feature not found")
    feature.enabled = body.enabled
    await db.flush()
    await db.refresh(feature)
    return feature


# ---------- LLM routing diagnostics ----------

@router.get("/llm-status")
async def llm_status(_: User = Depends(require_admin)):
    """The fallback chain as the server sees it: which entries are active, budget
    used in the last minute, cooldowns after 429s, disabled providers (bad key /
    no credits) and the last error of each entry."""
    from app.core.llm_router import get_router

    r = get_router()
    return {
        "chain": r.chain,
        "skipped_entries": r.skipped,
        "entries": r.status(),
    }
