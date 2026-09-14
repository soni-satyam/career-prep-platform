from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CandidateProfile(Base):
    """Structured candidate profile + raw resume text for RAG."""

    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_resume_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    structured: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    skills: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)
    experience_years: Mapped[Optional[float]] = mapped_column(nullable=True)
    source_filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="profiles")
