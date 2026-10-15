"""Dashboard data: saved jobs, application tracker, activity feed.

New tables only - created automatically by Base.metadata.create_all at startup,
nothing existing is altered.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


APPLICATION_STATUSES = ("applied", "interviewing", "offer", "rejected", "withdrawn")


class SavedJob(Base):
    """A job the user bookmarked from search (snapshot, because external listings expire)."""

    __tablename__ = "saved_jobs"
    __table_args__ = (UniqueConstraint("user_id", "job_uid", name="uq_saved_job_user_uid"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_uid: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    company: Mapped[str] = mapped_column(String(255), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(String(2048), default="")
    source: Mapped[str] = mapped_column(String(50), default="")
    source_label: Mapped[str] = mapped_column(String(80), default="")
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    salary_text: Mapped[str] = mapped_column(String(120), default="")
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    extra: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class JobApplication(Base):
    __tablename__ = "job_applications"
    __table_args__ = (Index("ix_job_app_user_status", "user_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    company: Mapped[str] = mapped_column(String(255), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(String(2048), default="")
    source_label: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(20), default="applied")
    applied_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_step: Mapped[str] = mapped_column(String(255), default="")
    next_step_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (Index("ix_activity_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(40))      # resume_uploaded | job_saved | application_added | application_status
    title: Mapped[str] = mapped_column(String(255))
    subtitle: Mapped[str] = mapped_column(String(255), default="")
    link: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
