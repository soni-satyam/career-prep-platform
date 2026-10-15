"""Dashboard + tracker API against a real (in-memory SQLite) database."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.jobsearch import service
from app.jobsearch.posting import JobPosting
from app.models import tracker as _t  # noqa: F401  (registers tables)
from app.models.job import Job
from app.models.profile import CandidateProfile
from app.models.session import PreparationSession
from app.models.tracker import JobApplication
from app.models.user import User

from tests.test_job_search import FakeSource, job


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(*_a, **_k):      # tests only: Postgres JSONB -> SQLite JSON
    return "JSON"


TABLES = ["users", "jobs", "candidate_profiles", "preparation_sessions", "saved_jobs", "job_applications", "activity_events"]


@pytest_asyncio.fixture
async def env(monkeypatch):
    from app.api import dashboard, job_search, profile, tracker
    from app.api.deps import get_current_user
    from app.core.database import get_db

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[Base.metadata.tables[t] for t in TABLES]))
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as s:
        s.add_all([User(id=1, email="a@x.com", is_active=True), User(id=2, email="b@x.com", is_active=True)])
        await s.commit()

    current = {"id": 1}

    async def fake_db():
        async with Session() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async def fake_user():
        async with Session() as s:
            return await s.get(User, current["id"])

    app = FastAPI()
    for r in (job_search.router, profile.router, tracker.router, dashboard.router):
        app.include_router(r, prefix="/api/v1")
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = fake_user
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    yield type("Env", (), {"c": client, "Session": Session, "current": current, "mp": monkeypatch})
    await client.aclose()
    await engine.dispose()


RESUME = ("Jane Doe\nBackend Engineer\nExperience\nAcme Jan 2020 - Present\n"
          "Python, Docker, AWS, PostgreSQL, Kafka, Redis, Kubernetes, Git services.\nEducation\nB.Tech 2012 - 2016\n")


@pytest.mark.asyncio
async def test_empty_dashboard(env):
    d = (await env.c.get("/api/v1/dashboard")).json()
    assert d["resume"]["uploaded"] is False and d["resume"]["next_steps"]
    assert d["stats"]["applications"] == 0 and d["stats"]["saved_jobs"] == 0
    assert d["activity"] == [] and d["saved_jobs"] == [] and d["applications"] == []


@pytest.mark.asyncio
async def test_resume_status_and_activity(env):
    r = await env.c.post("/api/v1/profile/resume", data={"text": RESUME})
    assert r.status_code == 200
    d = (await env.c.get("/api/v1/dashboard")).json()
    rs = d["resume"]
    assert rs["uploaded"] and rs["skills_count"] >= 8 and rs["completeness"] >= 85 and rs["stale"] is False
    assert [a["type"] for a in d["activity"]] == ["resume_uploaded"]

    # a stale resume is flagged and loses points
    async with env.Session() as s:
        p = (await s.execute(__import__("sqlalchemy").select(CandidateProfile))).scalar_one()
        p.updated_at = datetime.now(timezone.utc) - timedelta(days=120)
        await s.commit()
    rs2 = (await env.c.get("/api/v1/dashboard")).json()["resume"]
    assert rs2["stale"] and rs2["completeness"] < rs["completeness"] and any("120 days" in x for x in rs2["next_steps"])


@pytest.mark.asyncio
async def test_saved_jobs_flow(env):
    body = {"job_uid": "abc123def456", "title": "Backend Engineer", "company": "Zeta", "url": "https://z/1",
            "source": "greenhouse", "source_label": "Greenhouse", "match_score": 81}
    assert (await env.c.post("/api/v1/tracker/saved", json=body)).status_code == 201
    assert (await env.c.post("/api/v1/tracker/saved", json=body)).status_code == 201          # idempotent
    assert len((await env.c.get("/api/v1/tracker/saved")).json()) == 1
    assert (await env.c.get("/api/v1/tracker/saved/ids")).json() == {"saved": ["abc123def456"], "applied": []}
    d = (await env.c.get("/api/v1/dashboard")).json()
    assert d["stats"]["saved_jobs"] == 1 and d["saved_jobs"][0]["company"] == "Zeta"
    assert [a["title"] for a in d["activity"]] == ["Saved Backend Engineer"]                    # logged once, not twice
    await env.c.delete("/api/v1/tracker/saved/abc123def456")
    assert (await env.c.get("/api/v1/tracker/saved")).json() == []


@pytest.mark.asyncio
async def test_application_lifecycle_and_isolation(env):
    r = await env.c.post("/api/v1/tracker/applications", json={"title": "SDE II", "company": "Acme", "job_uid": "uid00001"})
    assert r.status_code == 201
    a = r.json()
    assert a["status"] == "applied" and a["applied_on"] == date.today().isoformat()
    again = (await env.c.post("/api/v1/tracker/applications", json={"title": "SDE II", "company": "Acme", "job_uid": "uid00001"})).json()
    assert again["id"] == a["id"]                                                                # one application per job

    p = await env.c.patch(f"/api/v1/tracker/applications/{a['id']}", json={"status": "interviewing", "next_step": "System design round",
                                                                          "next_step_date": (date.today() + timedelta(days=3)).isoformat()})
    assert p.status_code == 200 and p.json()["status"] == "interviewing"
    assert (await env.c.patch(f"/api/v1/tracker/applications/{a['id']}", json={"status": "bogus"})).status_code == 422
    assert (await env.c.get("/api/v1/tracker/applications", params={"status": "bogus"})).status_code == 422

    d = (await env.c.get("/api/v1/dashboard")).json()
    assert d["stats"]["interviewing"] == 1 and d["stats"]["active"] == 1 and d["stats"]["by_status"]["applied"] == 0
    assert d["upcoming"][0]["next_step"] == "System design round"
    assert [x["type"] for x in d["activity"]][:2] == ["application_status", "application_added"]
    assert (await env.c.get("/api/v1/tracker/saved/ids")).json()["applied"] == ["uid00001"]

    env.current["id"] = 2                                                                          # another user cannot touch it
    assert (await env.c.patch(f"/api/v1/tracker/applications/{a['id']}", json={"status": "offer"})).status_code == 404
    assert (await env.c.delete(f"/api/v1/tracker/applications/{a['id']}")).status_code == 404
    assert (await env.c.get("/api/v1/dashboard")).json()["stats"]["applications"] == 0
    env.current["id"] = 1
    assert (await env.c.delete(f"/api/v1/tracker/applications/{a['id']}")).status_code == 200
    assert (await env.c.get("/api/v1/dashboard")).json()["stats"]["applications"] == 0


@pytest.mark.asyncio
async def test_follow_up_and_sessions_in_feed(env):
    async with env.Session() as s:
        s.add(JobApplication(user_id=1, title="Old one", company="Foo", status="applied",
                             updated_at=datetime.now(timezone.utc) - timedelta(days=20)))
        s.add(JobApplication(user_id=1, title="Fresh", company="Bar", status="applied"))
        s.add(PreparationSession(user_id=1, title="Prep for Stripe", status="active", progress_pct=40.0))
        await s.commit()
    d = (await env.c.get("/api/v1/dashboard")).json()
    assert [x["title"] for x in d["follow_up"]] == ["Old one"]
    assert any(i["type"] == "session" and i["title"] == "Prep for Stripe" and i["link"].startswith("/sessions/") for i in d["activity"])
    assert d["stats"]["prep_sessions"] == 1


@pytest.mark.asyncio
async def test_recommended(env):
    env.mp.setattr(service, "build_sources", lambda s: [FakeSource("greenhouse", [
        job(source="greenhouse", title="Senior Backend Engineer", company="A", description="Python, Docker, AWS, Kafka. 3-6 years of experience.", posted=2),
        job(source="greenhouse", title="Backend Engineer", company="B", description="Python and Redis. 3-6 years of experience.", posted=3),
        job(source="greenhouse", title="Backend Engineer", company="Applied", description="Python Docker. 3-6 years of experience.", posted=3),
        job(source="greenhouse", title="Pastry Chef", company="C", description="Baking.", posted=1),
    ])])
    r = (await env.c.get("/api/v1/dashboard/recommended")).json()
    assert r["reason"] == "no_resume" and r["jobs"] == []

    await env.c.post("/api/v1/profile/resume", data={"text": RESUME})
    uid_applied = next(j.uid for j in [job(source="greenhouse", title="Backend Engineer", company="Applied",
                                           description="Python Docker. 3-6 years of experience.", posted=3)])
    await env.c.post("/api/v1/tracker/applications", json={"title": "Backend Engineer", "company": "Applied", "job_uid": uid_applied})
    r = (await env.c.get("/api/v1/dashboard/recommended", params={"limit": 5})).json()
    assert r["reason"] == "ok" and r["based_on"] == "Backend Engineer"
    companies = [j["company"] for j in r["jobs"]]
    assert "C" not in companies and "Applied" not in companies          # irrelevant + already-applied jobs left out
    scores = [j["match"]["score"] for j in r["jobs"]]
    assert scores == sorted(scores, reverse=True) and scores[0] >= 60
