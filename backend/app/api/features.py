"""Public feature flags (read-only for app clients)."""

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.feature import FeatureFlag

router = APIRouter(prefix="/features", tags=["features"])


class FeatureOut(BaseModel):
    key: str
    name: str
    description: str | None
    enabled: bool

    class Config:
        from_attributes = True


@router.get("", response_model=List[FeatureOut])
async def list_public_features(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FeatureFlag).order_by(FeatureFlag.key))
    return result.scalars().all()
