"""Company search: identification, career-page scraping, extra ATS connectors, SSRF guard, lookup and jobs.

All HTTP is mocked (httpx.MockTransport); DNS and the web-search / Wikipedia / LLM tools are faked.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.jobsearch import service as jobs_service
from app.jobsearch.company import net
from app.jobsearch.company import service as company_service
from app.jobsearch.company.careers import scrape_career_page
from app.jobsearch.company.discover import (
    detect_boards, extract_embedded_jobs, extract_founded, extract_job_links, find_career_links, parse_organization,
    parse_page,
)
from app.jobsearch.company.identify import (
    company_matches, domain_name_score, looks_like_url, pick_sites, slug_candidates,
)
from app.jobsearch.company.linkedin import parse_snippet, pick_linkedin
from app.jobsearch.company.sources import result_to_job
from app.jobsearch.company.overview import validate_llm
from app.jobsearch.company.service import Toolbox, company_jobs, lookup_company
from app.jobsearch.posting import SearchFilters
from app.jobsearch.sources.ats_extra import parse_recruitee, parse_smartrecruiters, parse_workable
from app.jobsearch.sources.base import SourceContext, TTLCache

HOME = """<html><head><title>Acme Robotics | Warehouse robots</title>
<meta name="description" content="Acme builds autonomous warehouse robots.">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Acme Robotics Pvt Ltd",
"foundingDate":"2019-04-01","description":"Autonomous robots for warehouses.",
"address":{"@type":"PostalAddress","addressLocality":"Pune","addressCountry":"IN"}}</script></head>
<body><nav><a href="/product">Product</a><a href="/blog/careers-tips">Careers tips</a><a href="/careers">Careers</a>
<a href="/about">About</a></nav><footer><a href="https://jobs.lever.co/acmerobotics">We're hiring</a></footer></body></html>"""

LISTING = """<html><head><title>Careers at Acme</title></head><body><h1>Open roles</h1>
<a href="/careers/backend-engineer"><div>Backend Engineer</div><div>Engineering</div><div>Pune, India</div></a>
<a href="/careers/product-designer"><span>Product Designer</span><span>Design · Remote</span></a>
<a href="/careers/ml-engineer"><h3>ML Engineer</h3><p>Bengaluru, India</p></a>
<a href="/careers">Careers</a><a href="/careers/apply">Apply</a></body></html>"""


def ld_job(title, loc, remote=False, kind="FULL_TIME"):
    extra = ',"jobLocationType":"TELECOMMUTE"' if remote else ""
    return (f'<html><head><script type="application/ld+json">{{"@context":"https://schema.org","@type":"JobPosting",'
            f'"title":"{title}","hiringOrganization":{{"name":"Acme Robotics"}},"employmentType":"{kind}",'
            f'"datePosted":"2026-10-01","description":"<p>Build robots. 3-5 years of experience.</p>",'
            f'"jobLocation":{{"address":{{"addressLocality":"{loc}","addressCountry":"IN"}}}}{extra}}}</script></head>'
            f'<body>{title}</body></html>')


def html(body, status=200):
    return httpx.Response(status, text=body, headers={"content-type": "text/html; charset=utf-8"})


def make_ctx(handler) -> SourceContext:
    return SourceContext(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), cache=TTLCache(), cache_ttl=60)


@pytest.fixture
def public_dns(monkeypatch):
    def fake(host, port, *a, **k):
        ip = "10.0.0.5" if "internal-host" in host else "93.184.216.34"
        return [(2, 1, 6, "", (ip, 0))]

    monkeypatch.setattr(net, "_resolve", fake)


# ------------------------------------------------------------------ identification


def test_identification_helpers():
    assert slug_candidates("Acme Robotics Pvt Ltd", "acmerobotics.io") == ["acmerobotics", "acme-robotics"]
    assert domain_name_score("stripe.com", "Stripe") == 3
    assert domain_name_score("tcs.com", "Tata Consultancy Services") == 2
    assert domain_name_score("random.com", "Stripe") == 0
    assert looks_like_url("acme.io") and looks_like_url("https://acme.io/careers") and not looks_like_url("acme robotics")
    # Wikipedia / LinkedIn style pages are never the company's own site
    res = [
        {"href": "https://en.wikipedia.org/wiki/Stripe", "title": "Stripe - Wikipedia", "body": "Stripe"},
        {"href": "https://www.linkedin.com/company/stripe", "title": "Stripe", "body": ""},
        {"href": "https://stripe.com/in", "title": "Stripe | Financial Infrastructure", "body": "payments"},
    ]
    assert [s.domain for s in pick_sites(res, "Stripe")] == ["stripe.com"]


def test_company_matches_is_token_based():
    assert company_matches("Stripe, Inc.", "Stripe")
    assert company_matches("Meta Platforms", "Meta")
    assert company_matches("Acme Technologies Pvt Ltd", "Acme")
    assert not company_matches("Metabase", "Meta")
    assert not company_matches("Stripe Capital", "Stripe")
    assert company_matches("Meta Platforms, Inc.", "Facebook", ["Meta Platforms"])


# ------------------------------------------------------------------ page parsing


def test_career_links_boards_and_org_facts():
    page = parse_page(HOME)
    links = find_career_links(page, "https://acme.io/")
    assert links[0].board is not None and links[0].board.provider == "lever" and links[0].board.slug == "acmerobotics"
    assert "https://acme.io/careers" in [l.url for l in links]
    assert all("blog" not in l.url for l in links)                      # "Careers tips" article is not the career page
    org = parse_organization(page.jsonld)
    assert org["founded"] == "2019" and org["headquarters"] == "Pune, IN" and org["name"] == "Acme Robotics Pvt Ltd"


def test_detect_boards_variants():
    found = detect_boards(
        '<script src="https://boards.greenhouse.io/embed/job_board/js?for=acmerobotics"></script>'
        '<a href="https://apply.workable.com/acme-io/j/ABC/">x</a> https://acme.recruitee.com/o/x '
        'https://boards.greenhouse.io/embed/job_app?token=1 https://jobs.smartrecruiters.com/Acme1/743')
    assert {(b.provider, b.slug) for b in found} == {
        ("greenhouse", "acmerobotics"), ("workable", "acme-io"), ("recruitee", "acme"), ("smartrecruiters", "Acme1")}


def test_job_link_groups_ignore_nav_links_and_embedded_json_ignores_team_lists():
    jobs = extract_job_links(parse_page(LISTING), "https://acme.io/careers")
    assert [j.title for j in jobs] == ["Backend Engineer", "Product Designer", "ML Engineer"]
    assert jobs[0].extras == ["Engineering", "Pune, India"]

    nd = ('<script id="__NEXT_DATA__" type="application/json">{"props":{"jobs":['
          '{"title":"SRE","url":"/careers/sre","location":"Remote","department":"Infra"},'
          '{"title":"Data Engineer","url":"/careers/de","locations":[{"name":"Pune"}],"team":"Data"}],'
          '"team":[{"name":"Ann","title":"CEO","url":"/team/ann"},{"name":"Bob","title":"CTO","url":"/team/bob"}]}}</script>')
    emb = extract_embedded_jobs(parse_page(nd), "https://acme.io/careers")
    assert [(e["title"], e["location"]) for e in emb] == [("SRE", "Remote"), ("Data Engineer", "Pune")]


def test_founded_extraction_is_conservative():
    assert extract_founded("Founded in 2015 in Bangalore") == "2015"
    assert extract_founded("Acme was founded by Jane Doe in 2012.") == "2012"
    assert extract_founded("Serving customers since 2010") is None
    assert extract_founded("launched in 2021") is None


def test_llm_founding_year_must_appear_in_evidence():
    ev = "Acme Robotics builds robots. Founded in 2019."
    ok = validate_llm({"summary": "Acme builds robots.", "founded": "2019"}, ev)
    bad = validate_llm({"summary": "Acme builds robots.", "founded": "2001"}, ev)
    assert ok.founded == "2019" and bad.founded is None
    assert validate_llm({"summary": "x", "founded": "unknown", "headquarters": "null"}, ev).headquarters is None


# ------------------------------------------------------------------ SSRF guard


@pytest.mark.asyncio
async def test_only_public_urls_are_fetched(public_dns):
    for bad in ("http://localhost/x", "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/",
                "http://10.1.2.3/", "http://internal-host.example/", "ftp://acme.io/", "https://acme.io:8443/", "file:///etc/passwd"):
        assert not await net.is_public_url(bad), bad
    assert await net.is_public_url("https://acme.io/careers")

    calls = []

    def handler(req):
        calls.append(str(req.url))
        if req.url.host == "acme.io":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
        return html("secret")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await net.safe_get(client, "https://acme.io/") is None          # redirect into the metadata service is refused
    assert calls == ["https://acme.io/"]


# ------------------------------------------------------------------ extra ATS connectors


def test_workable_smartrecruiters_recruitee_parsing():
    w = parse_workable({"name": "Acme Robotics", "jobs": [
        {"title": "Backend Engineer", "shortcode": "AB12", "url": "https://apply.workable.com/acme/j/AB12/",
         "employment_type": "Full-time", "telecommuting": True, "city": "Pune", "country": "India",
         "published_on": "2026-10-02", "description": "<p>Python. 2-4 years of experience.</p>"},
        {"title": "", "url": "x"}]}, "acme")
    assert len(w) == 1 and w[0].work_mode == "remote" and w[0].employment_type == "full-time" and w[0].location == "Pune, India"
    assert w[0].experience_min == 2 and w[0].posted_at is not None

    s = parse_smartrecruiters({"content": [
        {"id": "743", "name": "Data Analyst", "company": {"identifier": "Acme1", "name": "Acme Robotics"},
         "releasedDate": "2026-09-30T10:00:00.000Z", "location": {"city": "Pune", "country": "in", "remote": False},
         "typeOfEmployment": {"label": "Full-time"}}]}, "Acme1")
    assert s[0].url == "https://jobs.smartrecruiters.com/Acme1/743" and s[0].location == "Pune, IN"

    r = parse_recruitee({"offers": [
        {"id": 5, "title": "Designer", "careers_url": "https://acme.recruitee.com/o/designer", "remote": True,
         "employment_type_code": "fulltime", "status": "published", "published_at": "2026-10-03 08:00:00 UTC",
         "description": "<p>Design.</p>", "requirements": "<p>5+ years of experience</p>"},
        {"id": 6, "title": "Draft", "careers_url": "https://acme.recruitee.com/o/d", "status": "draft"}]}, "acme")
    assert len(r) == 1 and r[0].work_mode == "remote" and r[0].employment_type == "full-time" and r[0].experience_min == 5


# ------------------------------------------------------------------ career page scraping


@pytest.mark.asyncio
async def test_listing_links_are_followed_to_json_ld_detail_pages(public_dns):
    def handler(req):
        p = req.url.path
        if p == "/careers":
            return html(LISTING)
        if p == "/careers/backend-engineer":
            return html(ld_job("Backend Engineer", "Pune"))
        if p == "/careers/product-designer":
            return html(ld_job("Product Designer", "Remote", remote=True, kind="CONTRACTOR"))
        return html("gone", 404)                                          # ML Engineer's page is broken

    jobs, report = await scrape_career_page(make_ctx(handler), "https://acme.io/careers")
    by = {j.title: j for j in jobs}
    assert report.status == "ok" and report.jobs_found == 3
    assert by["Backend Engineer"].location == "Pune, IN" and by["Backend Engineer"].experience_min == 3
    assert by["Product Designer"].work_mode == "remote" and by["Product Designer"].employment_type == "contractor"
    assert by["ML Engineer"].location == "Bengaluru, India"               # fell back to what the listing link showed


@pytest.mark.asyncio
async def test_embedded_board_js_page_blocked_and_unreachable_are_reported(public_dns):
    page = "<html><head><title>Jobs</title></head><body><div id='gh'></div><script src='https://boards.greenhouse.io/embed/job_board/js?for=acmerobotics'></script></body></html>"
    jobs, rep = await scrape_career_page(make_ctx(lambda r: html(page)), "https://acme.io/careers")
    assert jobs == [] and rep.status == "boards_only" and [(b.provider, b.slug) for b in rep.boards] == [("greenhouse", "acmerobotics")]

    spa = "<html><body><div id='root'></div><script src='/static/app.js'></script></body></html>"
    _, rep = await scrape_career_page(make_ctx(lambda r: html(spa)), "https://acme.io/careers")
    assert rep.status == "js_rendered" and "JavaScript" in rep.note

    _, rep = await scrape_career_page(make_ctx(lambda r: html("no", 403)), "https://acme.io/careers")
    assert rep.status == "blocked"

    def boom(req):
        raise OSError("connection refused")

    _, rep = await scrape_career_page(make_ctx(boom), "https://acme.io/careers")
    assert rep.status == "unreachable"

    _, rep = await scrape_career_page(make_ctx(lambda r: html("<html><body>" + "We are a company. " * 80 + "</body></html>")), "https://acme.io/careers")
    assert rep.status == "empty"


@pytest.mark.asyncio
async def test_json_ld_on_the_listing_page_itself(public_dns):
    page = ld_job("Support Engineer", "Mumbai")
    jobs, rep = await scrape_career_page(make_ctx(lambda r: html(page)), "https://acme.io/careers")
    assert rep.status == "ok" and [j.title for j in jobs] == ["Support Engineer"]


# ------------------------------------------------------------------ lookup


def tools(search=None, wiki=("", ""), llm=None):
    async def default_llm(system, user):
        return {"summary": "Acme Robotics makes autonomous warehouse robots.", "what_it_does": "Builds warehouse robots.",
                "founded": "2019", "headquarters": "Pune, India", "industry": "Robotics"}

    return Toolbox(search=search or (lambda q, n: []), wikipedia=lambda name: wiki, llm=llm or default_llm)


def site_handler(req):
    if req.url.host in ("acme.io", "www.acme.io"):
        return html(HOME if req.url.path in ("", "/") else (LISTING if req.url.path == "/careers" else "nope"), 200 if req.url.path in ("", "/", "/careers") else 404)
    return html("nope", 404)


@pytest.mark.asyncio
async def test_lookup_by_name_builds_a_grounded_profile(public_dns):
    jobs_service.reset_cache(); company_service._profiles.clear()
    jobs_service.set_client(httpx.AsyncClient(transport=httpx.MockTransport(site_handler)))
    try:
        search = lambda q, n: ([  # noqa: E731
            {"href": "https://www.linkedin.com/company/acme-robotics", "title": "Acme Robotics | LinkedIn", "body": "Warehouse robots"},
            {"href": "https://acme.io/", "title": "Acme Robotics - Warehouse robots", "body": "Autonomous robots"},
            {"href": "https://acmerobotics-news.com/", "title": "Acme Robotics News", "body": "Industry blog"},
        ] if "official website" in q else [])
        p = await lookup_company("acme robotics", settings=Settings(), tools=tools(search=search))
    finally:
        jobs_service.set_client(None)
    assert p.name == "Acme Robotics" and p.website == "https://acme.io/" and p.confidence == "high"
    assert p.overview.founded == "2019" and p.overview.headquarters == "Pune, India" and p.overview.method == "llm"
    assert p.career_url == "https://acme.io/careers" and p.career_status == "found"      # own page preferred over the ATS link
    assert any(b.provider == "lever" and b.slug == "acmerobotics" for b in p.boards)
    assert p.alternatives and p.alternatives[0]["domain"] == "acmerobotics-news.com"      # other candidates are offered to the user
    assert {l["label"] for l in p.links} >= {"LinkedIn", "Naukri", "Indeed"}


@pytest.mark.asyncio
async def test_lookup_by_website_skips_search_and_survives_a_dead_llm(public_dns):
    jobs_service.reset_cache(); company_service._profiles.clear()
    jobs_service.set_client(httpx.AsyncClient(transport=httpx.MockTransport(site_handler)))
    searched = []

    async def dead(system, user):
        raise RuntimeError("quota")

    try:
        p = await lookup_company("acme.io", settings=Settings(),
                                 tools=tools(search=lambda q, n: searched.append(q) or [], llm=dead))
    finally:
        jobs_service.set_client(None)
    assert not any("official website" in q for q in searched)
    assert p.name == "Acme Robotics" and p.overview.method == "extracted"
    assert p.overview.summary.startswith("Autonomous robots") and p.overview.founded == "2019"


@pytest.mark.asyncio
async def test_lookup_rejects_an_invented_founding_year(public_dns):
    home = "<html><head><title>Zed</title><meta name='description' content='Zed sells paper.'></head><body>Zed sells paper to offices across the city.</body></html>"
    jobs_service.reset_cache(); company_service._profiles.clear()
    jobs_service.set_client(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: html(home) if r.url.path in ("", "/") else html("no", 404))))

    async def liar(system, user):
        return {"summary": "Zed sells paper.", "founded": "1987"}

    try:
        p = await lookup_company("zed.com", settings=Settings(), tools=tools(llm=liar))
    finally:
        jobs_service.set_client(None)
    assert p.overview.summary == "Zed sells paper." and p.overview.founded is None


@pytest.mark.asyncio
async def test_unknown_company_returns_a_low_confidence_profile_not_a_crash(public_dns):
    jobs_service.reset_cache(); company_service._profiles.clear()
    jobs_service.set_client(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: html("no", 404))))
    try:
        p = await lookup_company("Qwxzy Nonexistent Labs", settings=Settings(), tools=tools())
    finally:
        jobs_service.set_client(None)
    assert p.confidence == "low" and p.website == "" and p.notes


# ------------------------------------------------------------------ jobs for a company


LEVER = [
    {"id": "a1", "text": "Backend Engineer", "hostedUrl": "https://jobs.lever.co/acmerobotics/a1",
     "categories": {"location": "Pune, India", "commitment": "Full-time"}, "workplaceType": "hybrid",
     "createdAt": 1790000000000, "descriptionPlain": "About Acme Robotics. Python. 3-5 years of experience."},
    {"id": "a2", "text": "Software Engineering Intern", "hostedUrl": "https://jobs.lever.co/acmerobotics/a2",
     "categories": {"location": "Remote", "commitment": "Internship"}, "workplaceType": "remote",
     "createdAt": 1790000000000, "descriptionPlain": "Join Acme Robotics as an intern."},
]
JSEARCH = {"data": [
    {"job_title": "Site Reliability Engineer", "employer_name": "Acme Robotics, Inc.", "job_apply_link": "https://www.linkedin.com/jobs/view/1",
     "job_publisher": "LinkedIn", "job_city": "Bengaluru", "job_country": "IN", "job_description": "Keep robots online.", "job_id": "j1"},
    {"job_title": "Site Reliability Engineer", "employer_name": "Acme Robotics Staffing Co", "job_apply_link": "https://www.linkedin.com/jobs/view/2",
     "job_publisher": "LinkedIn", "job_description": "x", "job_id": "j2"},
    {"job_title": "Marketing Lead", "employer_name": "Acmeworks", "job_apply_link": "https://www.indeed.com/viewjob?jk=3",
     "job_publisher": "Indeed", "job_description": "x", "job_id": "j3"},
]}


def jobs_handler(seen):
    def handler(req):
        h = req.url.host or ""
        if h == "acme.io":
            if req.url.path == "/careers":
                return html("<html><head><title>Careers</title></head><body><a href='https://jobs.lever.co/acmerobotics'>See open roles</a></body></html>")
            return html("no", 404)
        if h == "api.lever.co":
            return httpx.Response(200, json=LEVER)
        if h == "jsearch.p.rapidapi.com":
            seen.append(req.url.params.get("query"))
            return httpx.Response(200, json=JSEARCH)
        return httpx.Response(404, json={})

    return handler


def web_search(q, n):
    return [{"href": "https://in.linkedin.com/jobs/view/product-manager-at-acme-robotics-77",
             "title": "Acme Robotics hiring Product Manager in Pune, Maharashtra, India | LinkedIn", "body": "Acme Robotics is hiring"},
            {"href": "https://www.naukri.com/job-listings-chef-other-co-1", "title": "Chef - Other Co - Pune", "body": "Other Co"}]


@pytest.mark.asyncio
async def test_company_jobs_combine_career_page_ats_aggregator_and_web_search_with_filters(public_dns):
    jobs_service.reset_cache(); company_service._profiles.clear()
    seen: list = []
    jobs_service.set_client(httpx.AsyncClient(transport=httpx.MockTransport(jobs_handler(seen))))
    try:
        prof = await lookup_company("Acme Robotics", website="https://acme.io/", settings=Settings(),
                                    tools=tools())
        prof.career_url = "https://acme.io/careers"
        prof.boards = []
        s = Settings(jsearch_api_key="k")
        out = await company_jobs(prof, SearchFilters(), None, settings=s, search=web_search)
        titles = {j.title: j for j, _ in out.result.jobs}

        assert set(titles) == {"Backend Engineer", "Software Engineering Intern", "Site Reliability Engineer", "Product Manager"}
        assert all(j.company == "Acme Robotics" for j, _ in out.result.jobs)         # canonical name on every job
        assert titles["Site Reliability Engineer"].source == "linkedin" and titles["Backend Engineer"].source == "lever"
        assert titles["Product Manager"].location == "Pune, Maharashtra, India"
        assert out.career is not None and out.career.status == "boards_only" and out.boards[0].provider == "lever"
        assert "Acme Robotics" in seen[0]                                         # aggregator was asked about this company
        assert not any("Marketing" in t or "Chef" in t for t in titles)           # other companies' jobs never leak in

        remote = await company_jobs(prof, SearchFilters(work_mode="remote"), None, settings=s, search=web_search)
        assert {j.title for j, _ in remote.result.jobs} == {"Software Engineering Intern"}
        intern = await company_jobs(prof, SearchFilters(employment_type="internship"), None, settings=s, search=web_search)
        assert {j.title for j, _ in intern.result.jobs} == {"Software Engineering Intern"}
        hybrid = await company_jobs(prof, SearchFilters(work_mode="hybrid"), None, settings=s, search=web_search)
        assert {j.title for j, _ in hybrid.result.jobs} == {"Backend Engineer"}
        keyword = await company_jobs(prof, SearchFilters(q="backend"), None, settings=s, search=web_search)
        assert [j.title for j, _ in keyword.result.jobs] == ["Backend Engineer"]
        assert "Acme Robotics backend" in seen[-1]
    finally:
        jobs_service.set_client(None)


@pytest.mark.asyncio
async def test_startup_board_is_found_by_guessing_the_slug_and_validated(public_dns):
    jobs_service.reset_cache(); company_service._profiles.clear()

    def handler(req):
        h, p = req.url.host or "", req.url.path
        if h == "api.lever.co" and p.endswith("/acmerobotics"):
            return httpx.Response(200, json=LEVER)
        if h == "api.ashbyhq.com" and p.endswith("/acmerobotics"):                      # same slug, someone else's board
            return httpx.Response(200, json={"jobs": [{"title": "Barista", "jobUrl": "https://jobs.ashbyhq.com/acmerobotics/x",
                                                     "descriptionPlain": "Pour coffee at Totally Different Cafe", "id": "x"}]})
        return httpx.Response(404, json={})

    jobs_service.set_client(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        from app.jobsearch.company.profile import CompanyProfile

        prof = CompanyProfile(key="acme-robotics", name="Acme Robotics", website="https://acme.io/", domain="acme.io")
        out = await company_jobs(prof, SearchFilters(), None, settings=Settings(), search=lambda q, n: [])
    finally:
        jobs_service.set_client(None)
    assert [(b.provider, b.slug) for b in out.boards] == [("lever", "acmerobotics")]      # Ashby's lookalike is rejected
    assert {j.title for j, _ in out.result.jobs} == {"Backend Engineer", "Software Engineering Intern"}


@pytest.mark.asyncio
async def test_a_career_page_that_fails_is_reported_not_hidden(public_dns, monkeypatch):
    jobs_service.reset_cache(); company_service._profiles.clear()
    from app.jobsearch.company.profile import CompanyProfile

    async def boom(ctx, url, **kw):
        raise RuntimeError("parser bug")

    monkeypatch.setattr(company_service, "scrape_career_page", boom)
    jobs_service.set_client(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404, json={}))))
    try:
        prof = CompanyProfile(key="acme", name="Acme", website="https://acme.io/", domain="acme.io",
                              career_url="https://acme.io/careers")
        out = await company_jobs(prof, SearchFilters(), None, settings=Settings(), search=lambda q, n: [])
    finally:
        jobs_service.set_client(None)
    assert out.career is not None and out.career.status == "unreachable"       # the UI says so instead of "no career page"
    assert out.result.total == 0


# ------------------------------------------------------------------ startups: LinkedIn-assisted lookup
# Snippet shapes below are modelled on how search engines show LinkedIn company pages; real snippets vary,
# which is why every field is optional.

LI_TAGLINE = {"href": "https://in.linkedin.com/company/acme-robotics-hq", "title": "Acme Robotics | LinkedIn",
              "body": "Acme Robotics | 5,123 followers on LinkedIn. Automating warehouses with AI | Acme Robotics is a robotics startup in Pune."}
LI_ABOUT = {"href": "https://www.linkedin.com/company/acme-robotics-hq/", "title": "Acme Robotics - LinkedIn",
            "body": "About us. We build warehouse robots. Website: https://acme.io. Industry: Robotics Engineering. "
                    "Company size: 11-50 employees. Headquarters: Pune, Maharashtra. Founded: 2023. Specialties: robotics, AI"}
LI_NO_SITE = {"href": "https://www.linkedin.com/company/acme-robotics-hq", "title": "Acme Robotics | LinkedIn",
              "body": "About us. We build warehouse robots. Industry: Robotics. Company size: 2-10 employees. "
                      "Headquarters: Pune. Founded: 2023."}


def test_linkedin_snippets_are_parsed_merged_and_filtered():
    f = parse_snippet(LI_ABOUT["body"])
    assert (f["website"], f["industry"], f["company size"], f["headquarters"], f["founded"]) == (
        "https://acme.io", "Robotics Engineering", "11-50 employees", "Pune, Maharashtra", "2023")
    t = parse_snippet(LI_TAGLINE["body"])
    assert t["followers"] == "5,123" and t["description"].startswith("Automating warehouses")

    other = {"href": "https://www.linkedin.com/company/other-co", "title": "Other Co | LinkedIn", "body": "Other Co | 10 followers on LinkedIn."}
    job = {"href": "https://www.linkedin.com/jobs/view/123", "title": "Acme Robotics hiring", "body": ""}
    hits = pick_linkedin([other, job, LI_TAGLINE, LI_ABOUT], "Acme Robotics")
    assert [h.slug for h in hits] == ["acme-robotics-hq"]                       # not the other company, not a job page
    assert hits[0].website == "https://acme.io" and hits[0].size == "11-50 employees"   # the two results were merged
    assert hits[0].jobs_url == "https://www.linkedin.com/company/acme-robotics-hq/jobs/"
    assert pick_linkedin([other], "Acme Robotics") == []


def li_search(li_results, ats_results=(), site_results=()):
    def search(q, n):
        if q.startswith("site:linkedin.com/company"):
            return list(li_results)
        if "official website" in q:
            return list(site_results)
        if "careers jobs" in q:
            return list(ats_results)
        return []
    return search


@pytest.mark.asyncio
async def test_startup_whose_site_search_misses_is_found_through_its_linkedin_page(public_dns):
    jobs_service.reset_cache(); company_service._profiles.clear()
    jobs_service.set_client(httpx.AsyncClient(transport=httpx.MockTransport(site_handler)))
    try:
        p = await lookup_company("acme robotics", settings=Settings(), tools=tools(search=li_search([LI_TAGLINE, LI_ABOUT])))
    finally:
        jobs_service.set_client(None)
    assert p.website == "https://acme.io/" and p.confidence == "medium"            # website came from the LinkedIn page
    assert p.name == "Acme Robotics"                                                 # properly cased from LinkedIn
    assert p.linkedin is not None and p.linkedin.slug == "acme-robotics-hq"
    assert p.overview.size == "11-50 employees"
    assert dict((l["label"], l["url"]) for l in p.links)["LinkedIn"] == "https://www.linkedin.com/company/acme-robotics-hq/jobs/"
    assert "https://www.linkedin.com/company/acme-robotics-hq/" in p.sources


@pytest.mark.asyncio
async def test_startup_with_no_website_at_all_still_gets_a_profile_from_linkedin(public_dns):
    jobs_service.reset_cache(); company_service._profiles.clear()
    jobs_service.set_client(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: html("no", 404))))
    try:
        p = await lookup_company("Acme Robotics", settings=Settings(), tools=tools(search=li_search([LI_NO_SITE]), llm=_dead_llm))
    finally:
        jobs_service.set_client(None)
    assert p.website == "" and p.confidence == "medium"
    assert p.overview.summary.startswith("We build warehouse robots")
    assert (p.overview.founded, p.overview.size, p.overview.headquarters, p.overview.industry) == ("2023", "2-10 employees", "Pune", "Robotics")
    assert any("LinkedIn" in n for n in p.notes)


async def _dead_llm(system, user):
    raise RuntimeError("no llm")


@pytest.mark.asyncio
async def test_job_board_found_via_search_hit_and_via_the_linkedin_slug(public_dns):
    jobs_service.reset_cache(); company_service._profiles.clear()
    hits = [{"href": "https://jobs.lever.co/acmerobotics/abc", "title": "Backend Engineer", "body": ""},
            {"href": "https://jobs.lever.co/unrelatedco/xyz", "title": "Chef", "body": ""}]
    jobs_service.set_client(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: html("no", 404))))
    try:
        p = await lookup_company("Acme Robotics", settings=Settings(),
                                 tools=tools(search=li_search([LI_NO_SITE], ats_results=hits), llm=_dead_llm))
    finally:
        jobs_service.set_client(None)
    assert [(b.provider, b.slug) for b in p.hint_boards] == [("lever", "acmerobotics")]      # lookalike slug dropped

    # the board is named after the LinkedIn slug, not after the company: still found, and verified
    def handler(req):
        if req.url.host == "api.lever.co" and req.url.path.endswith("/acme-robotics-hq"):
            return httpx.Response(200, json=LEVER)
        return httpx.Response(404, json={})

    jobs_service.set_client(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        out = await company_jobs(p, SearchFilters(), None, settings=Settings(), search=lambda q, n: [])
    finally:
        jobs_service.set_client(None)
    assert [(b.provider, b.slug) for b in out.boards] == [("lever", "acme-robotics-hq")]
    assert {j.title for j, _ in out.result.jobs} == {"Backend Engineer", "Software Engineering Intern"}


def test_startup_job_portals_are_recognised_in_web_results():
    r = {"href": "https://www.ycombinator.com/companies/acme-robotics/jobs/Ab12-founding-engineer",
         "title": "Founding Engineer at Acme Robotics | Y Combinator", "body": "Acme Robotics (YC S23) is hiring"}
    j = result_to_job(r, "Acme Robotics", [], "")
    assert j is not None and j.source == "yc" and j.title == "Founding Engineer"


@pytest.mark.asyncio
async def test_clicking_a_listed_company_pins_its_website_and_skips_the_ambiguous_search(public_dns):
    """The "popular companies" cards send name + website; the lookup must trust that site, not search for it."""
    jobs_service.reset_cache(); company_service._profiles.clear()
    jobs_service.set_client(httpx.AsyncClient(transport=httpx.MockTransport(site_handler)))
    queries: list[str] = []
    try:
        p = await lookup_company("Acme Robotics", website="https://acme.io", settings=Settings(),
                                 tools=tools(search=lambda q, n: queries.append(q) or []))
        again = await lookup_company("Acme Robotics", website="https://acme.io", settings=Settings(), tools=tools())
    finally:
        jobs_service.set_client(None)
    assert not any("official website" in q for q in queries)                 # no guessing which "Acme Robotics"
    assert p.website == "https://acme.io/" and p.name == "Acme Robotics" and p.confidence == "high"
    assert again is p                                                          # second click is served from cache
