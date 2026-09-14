from pathlib import Path
from functools import lru_cache
from typing import List, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[3] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "CareerPrep"
    environment: str = "development"
    debug: bool = True
    secret_key: str = "change-me-to-a-long-random-string"

    backend_host: str = "0.0.0.0"
    backend_port: int = 8001
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    frontend_url: str = "http://localhost:5173"
    backend_public_url: str = "http://localhost:8001"

    # Postgres
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "careerprep"
    postgres_password: str = "careerprep_secret"
    postgres_db: str = "careerprep"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # LLM providers
    google_api_key: str = ""
    groq_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    llm_provider: Literal["gemini", "groq", "openai"] = "gemini"
    chat_model: str = "gemini-3.8-flash"

    embedding_provider: Literal["gemini", "openai", "local"] = "gemini"
    embedding_model: str = "models/text-embedding-004"

    # OAuth - Google
    google_client_id: str = ""
    google_client_secret: str = ""

    # OAuth - GitHub
    github_client_id: str = ""
    github_client_secret: str = ""

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "careerprep"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # Auth / Session
    session_ttl_seconds: int = 86400
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # Bootstrap admin (created on first startup if set)
    admin_email: str = "admin@careerprep.local"
    admin_password: str = "admin12345"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
