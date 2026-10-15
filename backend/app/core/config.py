from pathlib import Path
from functools import lru_cache
from typing import List, Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[3] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "CareerPrep"
    environment: str = "development"
    # DEBUG no longer controls log volume (it used to switch on SQL echo).
    debug: bool = False
    secret_key: str = "change-me-to-a-long-random-string"

    backend_host: str = "0.0.0.0"
    backend_port: int = 8001
    cors_origins: str = "http://localhost:5174,http://localhost:3000"
    frontend_url: str = "http://localhost:5174"
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

    # Other providers. Blank key = that provider is skipped.
    openrouter_api_key: str = ""
    huggingface_api_key: str = Field(
        default="", validation_alias=AliasChoices("HUGGINGFACE_API_KEY", "HF_TOKEN")
    )
    # Optional extras you can add to LLM_CHAIN yourself (not in the default chain):
    cerebras_api_key: str = ""
    mistral_api_key: str = ""

    # --- LLM routing -------------------------------------------------------
    # Ordered fallback chain of `provider:model` entries, tried top to bottom.
    # Entries whose provider has no API key are skipped automatically.
    # Providers: groq, openrouter, gemini, huggingface, cerebras, mistral, openai.
    # (The model part may itself contain ':' e.g. "...-it:free".)
    llm_chain: str = (
        "groq:openai/gpt-oss-20b,"
        "openrouter:google/gemma-4-31b-it:free,"
        "openrouter:google/gemma-4-26b-a4b-it:free,"
        "gemini:gemini-3.5-flash-lite,"
        "huggingface:openai/gpt-oss-20b"
    )

    # Legacy single-provider settings, only used by the old app/core/llm.py helper.
    llm_provider: Literal["gemini", "groq", "openai"] = "gemini"
    chat_model: str = "gemini-3.8-flash"

    # Requests-per-minute budget WE enforce before calling (keep under the real
    # limit). OpenRouter and Hugging Face are account-wide, so all their chain
    # entries share one budget; Groq/Gemini limits are per model.
    groq_rpm: int = 25
    openrouter_rpm: int = 15
    gemini_rpm: int = 5
    huggingface_rpm: int = 10
    cerebras_rpm: int = 25
    mistral_rpm: int = 30
    openai_rpm: int = 60
    # Tokens-per-minute budget. Groq's free plan allows 8K TPM for gpt-oss-20b;
    # 0 = not enforced. Requests larger than this skip that entry.
    groq_tpm: int = 7000

    # gpt-oss on Groq / Hugging Face: low reasoning = far fewer hidden tokens
    # (matters with an 8K TPM budget). Blank = provider default.
    llm_reasoning_effort: str = "low"
    # Ask Groq for strict JSON output (fewer malformed responses).
    groq_json_mode: bool = True
    # Models whose name contains one of these get the system prompt folded into the
    # user message (Gemma rejects/ignores a separate system role on some hosts).
    llm_merge_system_for: str = "gemma"

    llm_request_timeout_seconds: int = 60
    # If every entry is at its budget, wait up to this long for a free slot
    # before returning a friendly "busy" error.
    llm_max_wait_seconds: int = 25
    # Max real provider calls for one logical request (keeps fallback small).
    llm_max_attempts: int = 4

    # Cache for pure-analysis agents (JD analysis, profile extraction, gaps).
    llm_cache_enabled: bool = True
    llm_cache_ttl_seconds: int = 86400

    # RAG ingestion embeds the JD + resume with Gemini after every session, but
    # nothing reads those vectors yet. Off by default to save Gemini calls.
    rag_ingest_enabled: bool = False

    embedding_provider: Literal["gemini", "openai", "local"] = "gemini"
    embedding_model: str = "models/text-embedding-004"

    # OAuth - Google
    google_client_id: str = ""
    google_client_secret: str = ""

    # OAuth - GitHub
    github_client_id: str = ""
    github_client_secret: str = ""

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "careerprep"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # Auth / Session
    session_ttl_seconds: int = 86400
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # --- Job search sources -------------------------------------------------
    # Official public job-board APIs (no key needed). Comma-separated board names.
    # Greenhouse token = the part in boards.greenhouse.io/<token>; Lever = jobs.lever.co/<site>;
    # Ashby = jobs.ashbyhq.com/<name>. Unknown / empty boards are skipped quietly.
    job_greenhouse_boards: str = "stripe,airbnb,cloudflare,databricks,figma,coinbase,discord,reddit,robinhood,dropbox"
    job_lever_companies: str = "palantir,spotify,plaid,cred"
    job_ashby_boards: str = "notion,ramp,linear,openai"
    # Direct company career pages that publish schema.org JobPosting JSON-LD, comma-separated URLs.
    job_career_page_urls: str = ""

    # Job aggregators that cover LinkedIn / Indeed / Naukri-style portals. Keys are optional;
    # a source without a key is simply skipped (and reported as such in the response).
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    jsearch_api_key: str = ""      # RapidAPI "JSearch": LinkedIn, Indeed, Glassdoor, ... listings
    jooble_api_key: str = ""
    job_remotive_enabled: bool = False   # remote-only; Remotive asks clients not to poll often

    job_default_country: str = "in"      # ISO-2, used by Adzuna / JSearch
    job_source_timeout_seconds: float = 10.0
    job_cache_ttl_seconds: int = 600
    job_max_results: int = 400

    # Company search (app/jobsearch/company)
    company_cache_ttl_seconds: int = 21600        # how long a looked-up company profile is reused
    company_lookup_timeout_seconds: float = 25.0  # hard cap for one lookup
    company_web_search_enabled: bool = True       # job pages found via web search (DuckDuckGo, no key)
    company_career_budget_seconds: float = 30.0   # max time spent reading one career page

    # Logging (see app/core/logging_config.py)
    log_level: str = "INFO"
    log_libs_level: str = "WARNING"
    log_sql: bool = False
    log_access: bool = True
    log_max_message_chars: int = 600

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
