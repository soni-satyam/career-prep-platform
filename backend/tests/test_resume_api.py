"""HTTP-level tests for edit → approve → download, using the real prep router with a fake DB/user."""

from __future__ import annotations

import copy
import io
from types import SimpleNamespace

import pytest
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.api import prep
from app.api.deps import get_current_user
from app.core.database import get_db
from app.services.ats_score import compare, unverified_skills
from app.services.readiness import verdict
from test_resume_export_and_match import JD, ORIGINAL, TAILORED

GAPS = {"overall_readiness": "almost", "strengths": ["Python"], "gaps": [{"id": "g", "severity": "high", "description": "No k8s"}]}


class FakeDB:
    def __init__(self, session):
        self.session = session
        self.flushed = 0

    async def get(self, model, pk):
        return self.session if pk == self.session.id else None

    async def flush(self):
        self.flushed += 1


@pytest.fixture
def env():
    match = compare(ORIGINAL, TAILORED, JD)
    session = SimpleNamespace(
        id=7, user_id=1, tailored_resume=copy.deepcopy(TAILORED), gap_analysis=GAPS,
        plan={"ats_match": match, "readiness": verdict(match, GAPS), "unverified_skills": unverified_skills(ORIGINAL, TAILORED),
              "original_resume_text": ORIGINAL},
    )
    db = FakeDB(session)
    app = FastAPI()
    app.include_router(prep.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), session, db, app


def test_templates_include_style_for_the_preview(env):
    c, *_ = env
    r = c.get("/api/v1/prep/resume-templates").json()
    assert r["default"] == "ats_classic" and {t["key"] for t in r["templates"]} == {"ats_classic", "ats_compact", "ats_serif"}
    assert r["templates"][0]["style"]["body"] > 0


def test_save_rescores_and_clears_approval(env):
    c, session, db, _ = env
    session.plan["resume_approval"] = {"approved_at": "x"}
    before = session.plan["ats_match"]["after"]["score"]
    edited = copy.deepcopy(TAILORED)
    edited["skills"] = ["Python"]; edited["summary"] = ""; edited["experience"] = []; edited["projects"] = []
    r = c.patch("/api/v1/prep/sessions/7/resume", json=edited)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ats_match"]["after"]["score"] < before
    assert body["ats_match"]["before"] == session.plan["ats_match"]["before"]
    assert body["readiness"]["level"] in {"needs_work", "significant_gap"}
    assert session.tailored_resume["skills"] == ["Python"]
    assert "resume_approval" not in session.plan          # edited after approval -> approve again
    assert db.flushed == 1


def test_save_flags_new_unverified_skills(env):
    c, *_ = env
    edited = copy.deepcopy(TAILORED); edited["skills"] = ["Python", "Rust", "Docker"]
    assert c.patch("/api/v1/prep/sessions/7/resume", json=edited).json()["unverified_skills"] == ["Rust"]


def test_save_rejects_oversized_resume(env):
    c, *_ = env
    edited = copy.deepcopy(TAILORED)
    edited["experience"] = [{"id": str(i), "title": "t", "content": "c"} for i in range(41)]
    assert c.patch("/api/v1/prep/sessions/7/resume", json=edited).status_code == 413


def test_approve_generates_validates_and_returns_links(env):
    c, session, *_ = env
    r = c.post("/api/v1/prep/sessions/7/resume/approve?template=ats_compact&page=letter")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["approved"] and b["validation"]["pdf"]["ok"] and b["validation"]["docx"]["ok"]
    assert [f["format"] for f in b["files"]] == ["pdf", "docx"]
    assert all(f["url"].startswith("/api/v1/prep/sessions/7/export-") and "template=ats_compact&page=letter" in f["url"] for f in b["files"])
    assert session.plan["resume_approval"]["template"] == "ats_compact"
    # the links really work and the files are the validated ones
    pdf = c.get(b["files"][0]["url"]); docx = c.get(b["files"][1]["url"])
    assert pdf.headers["content-type"] == "application/pdf" and "Rahul_Sharma_Resume.pdf" in pdf.headers["content-disposition"]
    assert len(PdfReader(io.BytesIO(pdf.content)).pages) == b["files"][0]["pages"]
    assert "Rahul Sharma" in "\n".join(p.text for p in Document(io.BytesIO(docx.content)).paragraphs)


def test_approve_blocked_when_a_file_fails_validation(env, monkeypatch):
    c, session, *_ = env
    bad = {"ok": False, "pages": 1, "checks": [{"id": "content", "label": "x", "status": "fail", "detail": "missing"}]}
    monkeypatch.setattr(prep, "validate_pdf", lambda *a, **k: bad)
    b = c.post("/api/v1/prep/sessions/7/resume/approve").json()
    assert b["approved"] is False and b["files"] == [] and "resume_approval" not in session.plan


def test_other_users_cannot_touch_the_session(env):
    c, _, _, app = env
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=2)
    assert c.patch("/api/v1/prep/sessions/7/resume", json=TAILORED).status_code == 404
    assert c.post("/api/v1/prep/sessions/7/resume/approve").status_code == 404
    assert c.get("/api/v1/prep/sessions/7/export-docx").status_code == 404
    assert c.get("/api/v1/prep/sessions/7/export-pdf").status_code == 404


def test_unknown_template_is_rejected(env):
    c, *_ = env
    assert c.post("/api/v1/prep/sessions/7/resume/approve?template=fancy").status_code == 422
    assert c.get("/api/v1/prep/sessions/7/export-docx?page=legal").status_code == 422


def test_original_resume_text_is_never_sent_to_the_browser():
    out = prep.SessionOut.model_validate(
        SimpleNamespace(id=1, title="t", status="s", progress_pct=0, plan={"original_resume_text": "SECRET", "ats_match": {}},
                        gap_analysis=None, tailored_resume=None, interview_pack=None))
    assert "original_resume_text" not in out.plan and "ats_match" in out.plan
