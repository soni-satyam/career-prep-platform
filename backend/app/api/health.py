from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(
    db: AsyncSession = Depends(get_db),
):
    db_ok = False
    redis_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    try:
        r = await get_redis()
        await r.ping()
        redis_ok = True
    except Exception:
        pass
    status = "ok" if db_ok and redis_ok else "degraded"
    return {
        "status": status,
        "postgres": "up" if db_ok else "down",
        "redis": "up" if redis_ok else "down",
    }
