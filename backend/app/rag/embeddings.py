"""Embedding helpers — free Gemini embeddings preferred."""

from __future__ import annotations

from typing import List

from app.core.config import get_settings


def get_embeddings():
    """Return an embeddings instance based on settings."""
    settings = get_settings()
    provider = settings.embedding_provider.lower()

    if provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY required for Gemini embeddings")
        return GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model,
            google_api_key=settings.google_api_key,
        )

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY required for OpenAI embeddings")
        return OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.openai_api_key,
        )

    # local fallback (sentence-transformers) can be added later
    raise ValueError(f"Unsupported embedding provider: {provider}")


async def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    emb = get_embeddings()
    # Most LangChain embeddings are sync
    return emb.embed_documents(texts)


async def embed_query(query: str) -> List[float]:
    emb = get_embeddings()
    return emb.embed_query(query)
