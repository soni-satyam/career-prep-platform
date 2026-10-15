from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tracker import ActivityEvent


async def log_activity(db: AsyncSession, user_id: int, type_: str, title: str, subtitle: str = "", link: str = "") -> None:
    """Record something worth showing in the dashboard feed. Never raises into the caller's request."""
    try:
        db.add(ActivityEvent(user_id=user_id, type=type_, title=title[:255], subtitle=subtitle[:255], link=link[:255]))
        await db.flush()
    except Exception:  # noqa: BLE001 - the feed is best-effort
        pass
