from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    slug: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    tech_stack: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    jobs = relationship("Job", back_populates="company", lazy="selectin")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), index=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    employment_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    seniority: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_jd_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    structured: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    skills_required: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company = relationship("Company", back_populates="jobs")
