"""RAG store: chunk text, embed, persist, retrieve via pgvector cosine similarity."""

from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag_chunk import DocumentChunk
from app.rag.embeddings import embed_query, embed_texts


def chunk_text(text: str, max_chars: int = 800, overlap: int = 100) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        # prefer break at sentence
        if end < len(text):
            for sep in [". ", "\n", "; "]:
                pos = text.rfind(sep, start, end)
                if pos > start + max_chars // 2:
                    end = pos + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = max(end - overlap, start + 1) if end < len(text) else end
    return chunks


async def ingest_text(
    db: AsyncSession,
    *,
    user_id: int,
    text_content: str,
    source_type: str,
    session_id: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> int:
    """Chunk + embed + store. Returns number of chunks written."""
    pieces = chunk_text(text_content)
    if not pieces:
        return 0
    try:
        vectors = await embed_texts(pieces)
    except Exception:
        # embeddings unavailable — store without vectors
        vectors = [None] * len(pieces)

    count = 0
    for i, (piece, vec) in enumerate(zip(pieces, vectors)):
        # pad/truncate to 768 dims if needed
        emb = None
        if vec is not None:
            emb = list(vec)
            if len(emb) > 768:
                emb = emb[:768]
            elif len(emb) < 768:
                emb = emb + [0.0] * (768 - len(emb))
        row = DocumentChunk(
            user_id=user_id,
            session_id=session_id,
            source_type=source_type,
            chunk_index=i,
            content=piece,
            metadata_=metadata or {},
            embedding=emb,
        )
        db.add(row)
        count += 1
    await db.flush()
    return count


async def retrieve(
    db: AsyncSession,
    *,
    user_id: int,
    query: str,
    session_id: Optional[int] = None,
    top_k: int = 6,
) -> list[dict[str, Any]]:
    """Return top-k relevant chunks for a query."""
    try:
        qvec = await embed_query(query)
        if len(qvec) > 768:
            qvec = qvec[:768]
        elif len(qvec) < 768:
            qvec = qvec + [0.0] * (768 - len(qvec))
    except Exception:
        # fallback: keyword-ish recent chunks
        stmt = select(DocumentChunk).where(DocumentChunk.user_id == user_id)
        if session_id:
            stmt = stmt.where(DocumentChunk.session_id == session_id)
        stmt = stmt.order_by(DocumentChunk.id.desc()).limit(top_k)
        result = await db.execute(stmt)
        return [
            {"content": c.content, "source_type": c.source_type, "score": 0.0}
            for c in result.scalars().all()
        ]

    # cosine distance via pgvector
    vec_literal = "[" + ",".join(str(float(x)) for x in qvec) + "]"
    sql = text(
        """
        SELECT id, content, source_type, metadata,
               1 - (embedding <=> CAST(:qvec AS vector)) AS score
        FROM document_chunks
        WHERE user_id = :user_id
          AND embedding IS NOT NULL
          AND (:session_id IS NULL OR session_id = :session_id)
        ORDER BY embedding <=> CAST(:qvec AS vector)
        LIMIT :top_k
        """
    )
    try:
        result = await db.execute(
            sql,
            {
                "qvec": vec_literal,
                "user_id": user_id,
                "session_id": session_id,
                "top_k": top_k,
            },
        )
        rows = result.fetchall()
        return [
            {
                "content": r.content,
                "source_type": r.source_type,
                "score": float(r.score or 0),
            }
            for r in rows
        ]
    except Exception:
        stmt = select(DocumentChunk).where(DocumentChunk.user_id == user_id).limit(top_k)
        result = await db.execute(stmt)
        return [
            {"content": c.content, "source_type": c.source_type, "score": 0.0}
            for c in result.scalars().all()
        ]
