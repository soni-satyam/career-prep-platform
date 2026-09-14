"""Require a feature flag to be enabled."""

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.feature import FeatureFlag


def require_feature(key: str):
    async def _dep(db: AsyncSession = Depends(get_db)) -> None:
        result = await db.execute(select(FeatureFlag).where(FeatureFlag.key == key))
        flag = result.scalar_one_or_none()
        if flag is not None and not flag.enabled:
            raise HTTPException(status_code=403, detail=f"Feature '{key}' is disabled")
    return _dep
