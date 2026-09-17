"""ATS match meter (before/after) and the ATS-friendly PDF export."""

from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from app.services.ats_score import build_terms, compare, resume_to_text, score_resume
from app.services.export_resume_pdf import TEMPLATES, render_resume_pdf

JD = {
    "title": "Backend Engineer",
    "tech_stack": ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "AWS"],
    "hard_skills": ["REST APIs", "CI/CD", "System design"],
    "keywords": ["microservices", "scalable"],
    "soft_skills": ["communication"],
}
ORIGINAL = """Rahul Sharma. Software developer. Built web apps with Python and Flask.
Used Postgres and some Docker. Worked in a team."""
TAILORED = {
    "profile": {"name": "Rahul Sharma", "email": "rahul@example.com", "phone": "+91 99999 99999", "city": "Lucknow, India", "github": "github.com/rahul"},
    "summary": "Backend engineer building scalable microservices with Python, FastAPI and PostgreSQL.",
    "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "AWS", "CI/CD", "REST APIs"],
    "experience": [{"id": "e1", "title": "Software Developer, Acme (2022 - Present)",
                    "content": "- Designed REST APIs serving 2M req/day & cut latency by 40%\n- Containerised services with Docker and deployed on AWS\n- Led system design for a scalable microservices platform"}],
    "projects": [{"id": "p1", "title": "Job Tracker", "content": "Built with FastAPI and PostgreSQL."}],
    "education": [{"id": "ed1", "school": "IIT Kanpur", "degree": "B.Tech", "major": "Computer Science", "start_date": "2018", "end_date": "2022"}],
    "awards": [{"id": "a1", "title": "Smart India Hackathon Finalist", "content": ""}],
}


# ------------------------------------------------------------------ match meter
def test_after_beats_before_and_reports_gains():
    m = compare(ORIGINAL, TAILORED, JD)
    assert m["before"]["score"] < m["after"]["score"]
    assert m["delta"] == m["after"]["score"] - m["before"]["score"] > 0
    assert "Kubernetes" in m["gained"] and "FastAPI" in m["gained"]
    assert "Python" in m["before"]["matched"] and "Python" not in m["gained"]
    assert 0 <= m["before"]["score"] <= 100 and 0 <= m["after"]["score"] <= 100


def test_same_terms_used_for_both_scores():
    m = compare(ORIGINAL, TAILORED, JD)
    assert m["before"]["total_terms"] == m["after"]["total_terms"]


def test_aliases_and_plurals_match():
    terms = build_terms({"tech_stack": ["JavaScript", "PostgreSQL", "Kubernetes", "REST APIs", "Machine Learning"]})
    r = score_resume("I know JS, postgres, k8s, RESTful api design and ML.", terms)
    assert r["score"] == 100, r


def test_whole_word_only_no_substring_false_positives():
    terms = build_terms({"tech_stack": ["Java", "Go", "R"]})
    r = score_resume("I use JavaScript and I am a good listener, working on the Gorilla project", terms)
    assert r["matched"] == []


def test_no_original_resume_gives_after_only():
    m = compare("", TAILORED, JD)
    assert m["before"] is None and m["delta"] is None and m["after"]["score"] > 0


def test_falls_back_to_jd_text_when_analysis_is_empty():
    m = compare(ORIGINAL, TAILORED, {}, "We need Python, Docker, Kubernetes and AWS experience for this role.")
    assert m and m["after"]["total_terms"] >= 3


def test_no_terms_means_no_meter():
    assert compare(ORIGINAL, TAILORED, {}, "") is None


# ------------------------------------------------------------------ PDF export
def _text(pdf: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


@pytest.mark.parametrize("template", list(TEMPLATES))
def test_pdf_is_valid_text_based_and_ats_structured(template):
    pdf = render_resume_pdf(TAILORED, template=template)
    assert pdf[:5] == b"%PDF-"
    r = PdfReader(io.BytesIO(pdf))
    assert r.metadata.title == "Rahul Sharma - Resume"
    txt = _text(pdf)
    # real, selectable text (not an image) with the headings ATS parsers look for, in reading order
    heads = [txt.index(h) for h in ["SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION", "AWARDS"]]
    assert heads == sorted(heads)
    assert "Rahul Sharma" in txt and "rahul@example.com" in txt
    assert "Designed REST APIs" in txt and "IIT Kanpur" in txt and "B.Tech Computer Science" in txt
    assert "&amp;" not in txt                       # '&' was escaped for the renderer, not leaked
    assert all(not page.images for page in r.pages)  # no images


def test_pdf_scores_the_same_as_the_data_it_came_from():
    """What an ATS reads back out of the PDF must still contain the JD keywords."""
    terms = build_terms(JD)
    from_pdf = score_resume(_text(render_resume_pdf(TAILORED)), terms)["score"]
    from_data = score_resume(resume_to_text(TAILORED), terms)["score"]
    assert from_pdf == from_data


def test_pdf_handles_unicode_empty_sections_and_long_content():
    weird = {"profile": {"name": "Zoë Ñandú"}, "summary": "Earned ₹12L — “top” performer … <b>x</b> & y",
             "experience": [{"title": "Role", "content": "\n".join(f"• line {i} " + "word " * 40 for i in range(120))}]}
    pdf = render_resume_pdf(weird, template="ats_compact", page="letter")
    assert len(PdfReader(io.BytesIO(pdf)).pages) >= 2
    assert "<b>x</b>" in _text(pdf)                 # markup in user text is shown literally, not interpreted
    assert render_resume_pdf({})[:5] == b"%PDF-"    # totally empty resume still renders
