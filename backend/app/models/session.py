from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PreparationSession(Base):
    """A preparation session tied to a user + target job / JD.

    Stores the generated plan, tailored resume, gap analysis,
    interview questions, quiz results, and progress metrics.
    """

    __tablename__ = "preparation_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    profile_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft")  # draft|active|completed
    # Aggregated progress 0-100
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    # Full plan, gap analysis, tailored content, Q&A, etc.
    plan: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    gap_analysis: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    tailored_resume: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    interview_pack: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    quiz_results: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="sessions")
