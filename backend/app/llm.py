"""PART 1b - One function that returns a chat model.

Every agent calls get_llm(), so swapping Groq <-> Gemini is a .env change only.
"""
from app import config


def get_llm(temperature: float = 0.3):
    if config.LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=config.GEMINI_MODEL,
            google_api_key=config.GOOGLE_API_KEY,
            temperature=temperature,
        )

    from langchain_groq import ChatGroq

    return ChatGroq(
        model=config.GROQ_MODEL,
        api_key=config.GROQ_API_KEY,
        temperature=temperature,
    )
