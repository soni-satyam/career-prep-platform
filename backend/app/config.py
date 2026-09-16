"""PART 1a - Central settings, read from the .env file."""
import os
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Free tiers have small token limits, so we trim long inputs.
MAX_RESUME_CHARS = 8000
MAX_JD_CHARS = 6000

# Input validation
MIN_RESUME_CHARS = 200
MIN_JD_CHARS = 100

# Quality-review loop
MAX_REGENERATIONS = 1          # extra generator runs allowed after the first
USE_LLM_REVIEW = os.getenv("USE_LLM_REVIEW", "true").lower() == "true"
MIN_SPECIFICITY_SCORE = 6      # LLM judge score (1-10) needed to approve

# Minimum questions per category the reviewer demands
MIN_PER_CATEGORY = {
    "technical": 3,
    "behavioral": 2,
    "company_specific": 2,
    "gap_based": 2,
    "role_specific": 1,
}

# ================= API / server settings =================
DB_PATH = os.getenv("DB_PATH", "data/career_prep.db")
CORS_ORIGINS = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:5174,http://localhost:3000").split(",") if o.strip()]
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "7"))            # resumes are auto-deleted after this
MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "2"))   # protects free-tier rate limits
RUN_TIMEOUT_SECONDS = int(os.getenv("RUN_TIMEOUT_SECONDS", "240"))
RATE_LIMIT_SESSIONS_PER_HOUR = int(os.getenv("RATE_LIMIT_SESSIONS_PER_HOUR", "10"))
RATE_LIMIT_PRACTICE_PER_HOUR = int(os.getenv("RATE_LIMIT_PRACTICE_PER_HOUR", "60"))
MAX_RESUME_FILE_MB = 5
MAX_JD_INPUT_CHARS = 20000
MAX_COMPANY_CHARS = 100


def llm_ready() -> bool:
    """True if the selected provider has an API key configured."""
    key = GOOGLE_API_KEY if LLM_PROVIDER == "gemini" else GROQ_API_KEY
    return bool(key.strip())
