"""Extract text from uploaded resume files (PDF / DOCX / plain text)."""

from __future__ import annotations

import io
from fastapi import HTTPException, UploadFile


async def extract_text_from_upload(file: UploadFile) -> str:
    filename = (file.filename or "").lower()
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")

    if filename.endswith(".pdf") or (file.content_type or "").startswith("application/pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            raise HTTPException(500, "pypdf not installed")
        reader = PdfReader(io.BytesIO(content))
        parts = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text)
        text = "\n".join(parts).strip()
        if not text:
            raise HTTPException(400, "Could not extract text from PDF")
        return text

    if filename.endswith(".docx") or "wordprocessingml" in (file.content_type or ""):
        try:
            from docx import Document
        except ImportError:
            raise HTTPException(500, "python-docx not installed")
        doc = Document(io.BytesIO(content))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()
        if not text:
            raise HTTPException(400, "Could not extract text from DOCX")
        return text

    if filename.endswith(".txt") or (file.content_type or "").startswith("text/"):
        try:
            return content.decode("utf-8").strip()
        except UnicodeDecodeError:
            return content.decode("latin-1").strip()

    raise HTTPException(
        400,
        "Unsupported file type. Upload PDF, DOCX, or TXT.",
    )
