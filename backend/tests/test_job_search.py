"""Job search: connectors (mock HTTP), filtering, priority ordering, dedupe, match %, API."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.jobsearch import service
from app.jobsearch.matching import CandidateProfileView, score_job
from app.jobsearch.posting import JobPosting, SearchFilters
from app.jobsearch.ranking import dedupe, passes_filters, sort_jobs
from app.jobsearch.sources.aggregators import AdzunaSource, JSearchSource, JoobleSource
from app.jobsearch.sources.ats import AshbySource, GreenhouseSource, LeverSource
from app.jobsearch.sources.base import JobSource, SourceContext, SourceNotConfigured, TTLCache
from app.jobsearch.sources.career_page import CareerPageSource, parse_job_postings
from app.jobsearch.text import (
    estimate_experience_years, extract_skills, html_to_text, location_matches, parse_experience,
)

NOW = datetime.now(timezone.utc)


def days_ago(n: float) -> datetime:
    return NOW - timedelta(days=n)


def job(title="Python Engineer", company="Acme", source="greenhouse", url=None, loc="Bengaluru", posted=1, **kw):
    return JobPosting(title=title, company=company, url=url or f"https://x/{source}/{title}/{company}",
                      source=source, location=loc, posted_at=days_ago(posted) if posted is not None else None, **kw)


def ctx(handler) -> SourceContext:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SourceContext(client=client, cache=TTLCache(), cache_ttl=60)


# ------------------------------------------------------------------ text utils

def test_html_and_skills_and_experience():
    assert html_to_text("&lt;p&gt;Hi &amp;amp; &lt;b&gt;bye&lt;/b&gt;&lt;/p&gt;") == "Hi & bye"
    skills = extract_skills("Python, Node.js, React, AWS, Postgres, C++, C#. Go to market. The rest of it. Java not JavaScript")
    assert {"Python", "Node.js", "React", "AWS", "PostgreSQL", "C++", "C#", "Java", "JavaScript"} <= set(skills)
    assert "Go" not in skills and "REST APIs" not in skills
    assert parse_experience("3-5 years of experience") == (3.0, 5.0)
    assert parse_experience("5+ years of relevant experience") == (5.0, None)
    assert location_matches("Bengaluru, Karnataka", "Bangalore")
    assert not location_matches("Pune", "Bangalore")


def test_resume_experience_ignores_education():
    resume = "Jane\nBackend Engineer\nExperience\nAcme  Jan 2019 - Present\nFoo 2016 - 2018\nEducation\nB.Tech 2012 - 2016\n"
    yrs = estimate_experience_years(resume, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert 8.5 < yrs < 9.5          # 2016-2018 + 2019-2026.08, NOT the degree years
    assert estimate_experience_years("I have 6+ years of experience in data") == 6.0


# ------------------------------------------------------------------ connectors

@pytest.mark.asyncio
async def test_greenhouse_lever_ashby_parse():
    def handler(req: httpx.Request) -> httpx.Response:
        u = str(req.url)
        if "greenhouse" in u:
            return httpx.Response(200, json={"jobs": [{
                "id": 1, "title": "Senior Python Engineer", "absolute_url": "https://gh/1",
                "location": {"name": "Bengaluru, India"}, "first_published": "2026-10-10T08:00:00Z",
                "content": "&lt;p&gt;5+ years of experience with Python and AWS&lt;/p&gt;",
                "pay_input_ranges": [{"min_cents": 3000000, "max_cents": 5000000, "currency_type": "USD"}]}]})
        if "lever" in u:
            return httpx.Response(200, json=[{
                "id": "abc", "text": "Backend Engineer", "hostedUrl": "https://lever/abc", "createdAt": 1760000000000,
                "categories": {"location": "Remote - India", "commitment": "Full-time"}, "workplaceType": "remote",
                "descriptionPlain": "3-5 years Go and Kubernetes",
                "salaryRange": {"min": 5000, "max": 8000, "currency": "USD", "interval": "per-month"}}])
        if "ashby" in u:
            return httpx.Response(200, json={"jobs": [{
                "id": "z", "title": "Data Scientist", "jobUrl": "https://ashby/z", "location": "Remote", "isRemote": True,
                "publishedAt": "2026-10-12T00:00:00.000+00:00", "employmentType": "FullTime",
                "descriptionPlain": "Machine learning, PyTorch",
                "compensation": {"summaryComponents": [{"compensationType": "Salary", "interval": "1 YEAR",
                                                         "currencyCode": "USD", "minValue": 120000, "maxValue": 150000}]}}]})
        return httpx.Response(404)

    c = ctx(handler)
    gh = await GreenhouseSource("stripe").fetch(c, SearchFilters())
    assert gh[0].source == "greenhouse" and gh[0].company == "Stripe"
    assert (gh[0].experience_min, gh[0].salary_min, gh[0].salary_currency) == (5.0, 30000.0, "USD")
    assert "Python and AWS" in gh[0].description and gh[0].posted_at.year == 2026

    lv = await LeverSource("palantir").fetch(c, SearchFilters())
    assert lv[0].remote and lv[0].salary_min == 60000 and lv[0].experience_max == 5.0

    ab = await AshbySource("notion").fetch(c, SearchFilters())
    assert ab[0].remote and ab[0].salary_max == 150000 and ab[0].employment_type == "full-time"


@pytest.mark.asyncio
async def test_board_failure_is_isolated_and_all_failing_raises():
    def handler(req):
        return httpx.Response(200, json={"jobs": []}) if "good" in str(req.url) else httpx.Response(404)
    c = ctx(handler)
    assert await GreenhouseSource("good,missing").fetch(c, SearchFilters()) == []     # one bad board is fine
    with pytest.raises(RuntimeError):
        await GreenhouseSource("missing1,missing2").fetch(ctx(handler), SearchFilters())


def test_career_page_json_ld():
    page = """<html><script type="application/ld+json">{"@context":"https://schema.org","@graph":[
      {"@type":"JobPosting","title":"ML Engineer","datePosted":"2026-10-13","description":"<p>2+ years of experience, Python</p>",
       "hiringOrganization":{"name":"Zeta"},"jobLocation":{"address":{"addressLocality":"Pune","addressCountry":"IN"}},
       "baseSalary":{"currency":"INR","value":{"minValue":2000000,"maxValue":3000000,"unitText":"YEAR"}},
       "employmentType":"FULL_TIME","url":"https://zeta.in/jobs/1"}]}</script></html>"""
    [j] = parse_job_postings(page, "https://zeta.in/careers")
    assert (j.company, j.location, j.source, j.salary_min, j.employment_type) == ("Zeta", "Pune, IN", "career_page", 2000000.0, "full-time")


@pytest.mark.asyncio
async def test_aggregators_parse_and_publisher_mapping():
    def handler(req):
        u = str(req.url)
        if "adzuna" in u:
            assert "what=python" in u and "where=Bangalore" in u
            return httpx.Response(200, json={"results": [{"id": 9, "title": "Python Dev", "redirect_url": "https://adz/9",
                "company": {"display_name": "Foo"}, "location": {"display_name": "Bengaluru"}, "created": "2026-10-13T00:00:00Z",
                "salary_min": 1500000, "salary_max": 2500000, "description": "3 years of experience"}]})
        if "jsearch" in u:
            return httpx.Response(200, json={"data": [
                {"job_id": "a", "job_title": "Python Dev", "employer_name": "Foo", "job_publisher": "LinkedIn",
                 "job_apply_link": "https://li/a", "job_city": "Bengaluru", "job_posted_at_datetime_utc": "2026-10-13T00:00:00Z",
                 "job_min_salary": 100000, "job_max_salary": 200000, "job_salary_currency": "INR", "job_salary_period": "MONTH"},
                {"job_id": "b", "job_title": "Python Dev II", "employer_name": "Bar", "job_publisher": "Naukri.com", "job_apply_link": "https://n/b"}]})
        if "jooble" in u:
            return httpx.Response(200, json={"jobs": [{"id": 1, "title": "Python Dev", "company": "Baz", "link": "https://j/1",
                "location": "Pune", "source": "indeed.com", "updated": "2026-10-12T10:00:00.0000000"}]})
        return httpx.Response(404)
    c = ctx(handler)
    f = SearchFilters(q="python", location="Bangalore", country="in")
    adz = await AdzunaSource("id", "key").fetch(c, f)
    assert adz[0].salary_currency == "INR" and adz[0].experience_min == 3.0
    js = await JSearchSource("k").fetch(c, f)
    assert [j.source for j in js] == ["linkedin", "naukri"] and js[0].salary_min == 1_200_000   # monthly -> annual
    jo = await JoobleSource("k").fetch(c, f)
    assert jo[0].source == "indeed"
    with pytest.raises(SourceNotConfigured):
        await AdzunaSource("", "").fetch(c, f)


# --------------------------------------------------------------------- ranking

def test_priority_then_recency_ordering():
    jobs = [
        job(source="indeed", posted=0.1, title="A"),
        job(source="lever", posted=5, title="B"),
        job(source="greenhouse", posted=9, title="C"),
        job(source="greenhouse", posted=2, title="D"),
        job(source="career_page", posted=30, title="E"),
        job(source="linkedin", posted=1, title="F"),
        job(source="other", posted=0.5, title="G"),
        job(source="naukri", posted=3, title="H"),
    ]
    order = [j.title for j in sort_jobs(jobs, "priority")]
    assert order == ["E", "D", "C", "B", "F", "H", "A", "G"]      # career page, GH (newest first), lever, LI, Naukri, Indeed, other
    assert [j.title for j in sort_jobs(jobs, "recent")][:3] == ["A", "G", "F"]


def test_dedupe_keeps_best_source_and_records_others():
    a = job(source="indeed", url="https://i/1", title="Sr. Python Engineer", company="Acme Inc")
    b = job(source="greenhouse", url="https://g/1", title="Senior Python Engineer", company="Acme", loc="Bengaluru, India")
    c = job(source="linkedin", url="https://l/1", title="Senior Python Engineer (Remote)", company="ACME LLC")
    out = dedupe([a, b, c])
    assert len(out) == 1 and out[0].source == "greenhouse"
    assert {x["source"] for x in out[0].also_on} == {"indeed", "linkedin"}


def test_filters():
    f = lambda **k: SearchFilters(**k)           # noqa: E731
    base = job(salary_min=2_000_000, salary_max=3_000_000, salary_currency="INR", experience_min=3, experience_max=5,
               employment_type="full-time", posted=2)
    assert passes_filters(base, f(salary_min=2_500_000, salary_currency="INR"), search_locally=False)
    assert not passes_filters(base, f(salary_min=3_500_000, salary_currency="INR"), search_locally=False)
    assert passes_filters(base, f(salary_min=3_500_000, salary_currency="USD"), search_locally=False)       # not comparable
    assert not passes_filters(base, f(salary_min=3_500_000, salary_currency="USD", include_unspecified_salary=False), search_locally=False)
    assert not passes_filters(job(), f(salary_min=1, include_unspecified_salary=False), search_locally=False)
    assert passes_filters(base, f(experience_min=4, experience_max=8), search_locally=False)
    assert not passes_filters(base, f(experience_min=6, experience_max=9), search_locally=False)
    assert passes_filters(base, f(location="Bangalore"), search_locally=False)
    assert not passes_filters(base, f(location="Mumbai"), search_locally=False)
    assert passes_filters(job(remote=True, work_mode="remote", loc="Anywhere"), f(location="Mumbai"), search_locally=False)
    assert not passes_filters(job(), f(work_mode="remote"), search_locally=False)
    assert passes_filters(base, f(posted_within_days=3), search_locally=False)
    assert not passes_filters(base, f(posted_within_days=1), search_locally=False)
    assert not passes_filters(job(posted=None), f(posted_within_days=7), search_locally=False)
    assert not passes_filters(base, f(employment_type="contract"), search_locally=False)
    assert passes_filters(base, f(q="python developer"), search_locally=True)
    assert not passes_filters(job(title="Sales Manager"), f(q="python developer"), search_locally=True)


# -------------------------------------------------------------------- matching

def test_match_scores():
    p = CandidateProfileView(skills=["python", "AWS", "Docker"], title="Backend Engineer", experience_years=4)
    strong = job(title="Backend Engineer", description="Python, AWS, Docker. 3-5 years of experience.")
    weak = job(title="Android Developer", description="Kotlin, Android, Jetpack. 3-5 years of experience.")
    s, w = score_job(strong, p), score_job(weak, p)
    assert s.score >= 90 and set(s.matched_skills) == {"Python", "AWS", "Docker"}
    assert w.score < 50 and "Kotlin" in w.missing_skills
    assert score_job(strong, CandidateProfileView()) is None                 # no profile -> no match shown
    # missing job skills must not count as 0%: only title/experience are used
    only_title = score_job(job(title="Backend Engineer", description="Great team."), p)
    assert only_title.parts["skills"] is None and only_title.score >= 70
    # over-experienced gets a mild penalty only
    senior = CandidateProfileView(skills=["Python"], title="Backend Engineer", experience_years=15)
    assert score_job(job(title="Backend Engineer", description="Python 2-4 years of experience"), senior).score >= 75


# --------------------------------------------------------------------- service

class FakeSource(JobSource):
    def __init__(self, name, jobs=None, err=None, server_side=False, configured=True):
        self.name, self._jobs, self._err, self.server_side_search, self._conf = name, jobs or [], err, server_side, configured

    def configured(self): return self._conf
    def not_configured_hint(self): return "set a key"

    async def fetch(self, ctx, f):
        if self._err:
            raise self._err
        return list(self._jobs)


@pytest.mark.asyncio
async def test_service_end_to_end_with_isolation_and_match():
    srcs = [
        FakeSource("greenhouse", [job(source="greenhouse", title="Backend Engineer", description="Python AWS. Python services.", posted=3),
                                  job(source="greenhouse", title="Chef", description="Cooking")]),
        FakeSource("lever", [job(source="lever", title="Python Developer", company="Zed", description="Python Docker", posted=1)]),
        FakeSource("jsearch", err=httpx.ReadTimeout("slow"), server_side=True),
        FakeSource("adzuna", configured=False, server_side=True),
        FakeSource("jooble", [job(source="indeed", title="Python Engineer", company="Q", description="Python", posted=0.2)], server_side=True),
    ]
    prof = CandidateProfileView(skills=["Python", "AWS"], title="Backend Engineer", experience_years=3)
    res = await service.search_jobs(SearchFilters(q="python"), prof, sources=srcs)
    titles = [j.title for j, _ in res.jobs]
    assert "Chef" not in titles                                              # irrelevant ATS job filtered locally
    # title relevance first (Python in the title), then source tier; description-only mention last
    assert [j.source for j, _ in res.jobs] == ["lever", "indeed", "greenhouse"]
    st = {s.name: s for s in res.sources}
    assert st["jsearch"].status == "error" and st["adzuna"].status == "skipped" and st["lever"].status == "ok"
    assert res.profile_used and all(m is not None for _, m in res.jobs)
    # without a profile: no match info
    res2 = await service.search_jobs(SearchFilters(q="python"), None, sources=srcs)
    assert not res2.profile_used and all(m is None for _, m in res2.jobs)
    # sort by match
    res3 = await service.search_jobs(SearchFilters(q="python", sort="match"), prof, sources=srcs)
    scores = [m.score for _, m in res3.jobs]
    assert scores == sorted(scores, reverse=True)
    # source filter incl. "other" bucket
    res4 = await service.search_jobs(SearchFilters(q="python", sources=["lever"]), None, sources=srcs)
    assert [j.source for j, _ in res4.jobs] == ["lever"]
    # pagination
    res5 = await service.search_jobs(SearchFilters(q="python"), None, page=2, page_size=2, sources=srcs)
    assert res5.total == 3 and len(res5.jobs) == 1


# ------------------------------------------------------------------------- API

class _Res:
    def scalar_one_or_none(self): return None


class FakeDB:
    async def execute(self, *a, **k): return _Res()


def _client(monkeypatch, jobs):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import job_search
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.models.user import User

    app = FastAPI()
    app.include_router(job_search.router, prefix="/api/v1")
    user = User(id=1, email="a@b.c", is_active=True, current_role="Backend Engineer")

    async def fake_db(): yield FakeDB()
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(service, "build_sources", lambda s: [FakeSource("greenhouse", jobs)])
    return TestClient(app)


def test_api_search_shape_and_validation(monkeypatch):
    c = _client(monkeypatch, [job(source="greenhouse", title="Backend Engineer", description="Python AWS", posted=1,
                                   salary_min=1, salary_max=2, salary_currency="INR")])
    r = c.get("/api/v1/jobs/search", params={"q": "backend", "sort": "priority", "sources": ["greenhouse", "lever"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1 and body["results"][0]["source_label"] == "Greenhouse" and body["results"][0]["source_tier"] == 1
    assert body["profile_used"] is False and body["results"][0]["match"] is None     # no resume -> plain results
    assert c.get("/api/v1/jobs/search", params={"sort": "bogus"}).status_code == 422
    assert c.get("/api/v1/jobs/search/meta").json()["sources"][0]["key"] == "career_page"


# ------------------------------------------------------- profile upload + match

class _ProfDB:
    def __init__(self): self.added = []; self.row = None
    async def execute(self, *a, **k):
        r = _Res()
        row = None if "feature_flags" in str(a[0]) else self.row      # feature-flag lookup -> no flag row
        r.scalar_one_or_none = lambda: row
        return r
    def add(self, o): self.added.append(o); self.row = o
    async def flush(self): pass
    async def refresh(self, o): pass
    async def delete(self, o): self.row = None


def test_resume_upload_then_match(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import job_search, profile
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.models.user import User

    db = _ProfDB()
    app = FastAPI()
    app.include_router(job_search.router, prefix="/api/v1")
    app.include_router(profile.router, prefix="/api/v1")

    async def fake_db(): yield db
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = lambda: User(id=1, email="a@b.c", is_active=True)
    monkeypatch.setattr(service, "build_sources", lambda s: [FakeSource("greenhouse", [
        job(source="greenhouse", title="Backend Engineer", description="Python, Docker, Kubernetes. 3-5 years of experience.", posted=1),
        job(source="greenhouse", title="Android Engineer", company="Z", description="Kotlin and Android. 3-5 years of experience.", posted=1)])])
    c = TestClient(app)

    assert c.get("/api/v1/profile").json()["has_profile"] is False
    resume = ("Jane Doe\nBackend Engineer\njane@x.com\nExperience\nAcme  Jan 2020 - Present\n"
              "Built services in Python and Docker on AWS with Postgres.\nEducation\nB.Tech 2012 - 2016\n")
    r = c.post("/api/v1/profile/resume", data={"text": resume})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["has_profile"] and p["title"] == "Backend Engineer" and {"Python", "Docker", "AWS", "PostgreSQL"} <= set(p["skills"])
    assert 5 < p["experience_years"] < 8

    res = c.get("/api/v1/jobs/search", params={"q": "engineer", "sort": "match"}).json()
    assert res["profile_used"] is True
    assert res["results"][0]["title"] == "Backend Engineer" and res["results"][0]["match"]["score"] > res["results"][1]["match"]["score"]
    assert "Kubernetes" in res["results"][0]["match"]["missing_skills"]

    edited = c.patch("/api/v1/profile", json={"skills": ["python", "kubernetes"], "experience_years": 4}).json()
    assert edited["skills"] == ["Python", "Kubernetes"] and edited["experience_years"] == 4
    assert c.post("/api/v1/profile/resume", data={"text": "short"}).status_code == 400
