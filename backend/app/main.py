from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from app.api import admin, auth, features, health, job_search, jobs, live_interview, prep, profile, quizzes, users
from app.core.config import get_settings
from app.core.logging_config import setup_logging
from app.core.errors import register_exception_handlers
from app.core.database import AsyncSessionLocal, Base, engine
from app.core.redis import close_redis, get_redis
from app.core.security import hash_password
from app.models.feature import FeatureFlag
from app.models.user import User

settings = get_settings()
setup_logging(settings)

DEFAULT_FEATURES = [
    ("resume_tailor", "Resume Tailoring", "AI-powered resume customization for a JD"),
    ("job_search", "Job Search", "Search and browse job listings"),
    ("company_search", "Company Search", "Explore companies and tech stacks"),
    ("interview_prep", "Interview Prep", "AI-generated interview questions"),
    ("quizzes", "Practice Quizzes", "Skill quizzes with instant feedback"),
    ("prep_plan", "Preparation Plans", "Full multi-week plan generation"),
    ("progress_tracking", "Progress Tracking", "Track completion across modules"),
]


async def seed_defaults():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == settings.admin_email))
        admin = result.scalar_one_or_none()
        if not admin:
            admin = User(
                email=settings.admin_email,
                hashed_password=hash_password(settings.admin_password),
                full_name="Admin",
                is_superuser=True,
                is_active=True,
            )
            db.add(admin)

        for key, name, desc in DEFAULT_FEATURES:
            existing = await db.execute(select(FeatureFlag).where(FeatureFlag.key == key))
            if not existing.scalar_one_or_none():
                db.add(FeatureFlag(key=key, name=name, description=desc, enabled=True))

        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    await get_redis()
    await seed_defaults()
    from app.core.llm_router import get_router

    get_router()  # builds the LLM fallback chain and logs it (and any missing keys)
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description="AI Career Preparation Platform — multi-agent + RAG",
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(prep.router, prefix="/api/v1")
app.include_router(job_search.router, prefix="/api/v1")  # must be before jobs: "/jobs/search" vs "/jobs/{job_id}"
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(profile.router, prefix="/api/v1")
app.include_router(quizzes.router, prefix="/api/v1")
app.include_router(live_interview.router, prefix="/api/v1")
app.include_router(features.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"name": settings.app_name, "version": "0.4.0", "docs": "/docs"}
