"""pgvector document chunks for RAG over profile + JD."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Vector type — pgvector
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None  # type: ignore


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("preparation_sessions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_type: Mapped[str] = mapped_column(String(50))  # resume | jd | profile
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)
    # embedding stored as vector(768) for Gemini text-embedding-004 / or 1536 for OpenAI
    # We use a flexible approach: store as ARRAY if vector extension issues
    embedding: Mapped[Optional[list]] = mapped_column(
        Vector(768) if Vector else JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
