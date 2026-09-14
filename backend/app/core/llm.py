"""LLM factory — supports free providers (Gemini primary, Groq secondary)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import get_settings


def get_chat_model(
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    **kwargs: Any,
) -> BaseChatModel:
    """Return a chat model based on settings or explicit override.

    Priority:
      1. Explicit provider/model args
      2. Settings.LLM_PROVIDER + CHAT_MODEL
    """
    settings = get_settings()
    provider = (provider or settings.llm_provider).lower()
    model = model or settings.chat_model

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not settings.google_api_key:
            raise ValueError(
                "GOOGLE_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey"
            )
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.google_api_key,
            temperature=temperature,
            **kwargs,
        )

    if provider == "groq":
        from langchain_groq import ChatGroq

        if not settings.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is not set. Get a free key at https://console.groq.com"
            )
        return ChatGroq(
            model=model,
            api_key=settings.groq_api_key,
            temperature=temperature,
            **kwargs,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set.")
        return ChatOpenAI(
            model=model,
            api_key=settings.openai_api_key,
            temperature=temperature,
            **kwargs,
        )

    raise ValueError(f"Unsupported LLM provider: {provider}. Use gemini | groq | openai")


@lru_cache
def get_default_chat_model() -> BaseChatModel:
    """Cached default model from settings."""
    return get_chat_model()
