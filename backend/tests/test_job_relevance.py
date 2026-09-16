"""Role-search relevance: title first, unrelated titles filtered, related titles kept."""

from __future__ import annotations

from datetime import datetime, timezone

from app.jobsearch.posting import JobPosting, SearchFilters
from app.jobsearch.ranking import passes_filters, sort_jobs
from app.jobsearch.relevance import EXACT, KEYWORD, RELATED, score_title

AI_DESC = "We build products using AI and machine learning. Python, AI tooling, AI-assisted workflows. AI AI."


def j(title, desc="", source="greenhouse", company="Acme"):
    return JobPosting(title=title, company=company, url=f"https://x/{title}/{company}/{source}", source=source,
                      location="Bengaluru", description=desc, posted_at=datetime.now(timezone.utc))


def keeps(q, title, desc=""):
    return passes_filters(j(title, desc), SearchFilters(q=q), search_locally=False)


# ---- rule 2: unrelated titles are filtered even if the description screams AI ----------------
def test_generic_software_engineer_is_filtered_for_ai_engineer():
    assert not keeps("AI Engineer", "Software Engineer", AI_DESC)
    assert not keeps("AI Engineer", "Senior Backend Engineer", AI_DESC)
    assert not keeps("AI Engineer", "Full Stack Developer", "Python machine learning AI AI")
    assert not keeps("AI Engineer", "Data Analyst", AI_DESC)
    assert not keeps("AI Engineer", "AI Product Manager", AI_DESC)          # wrong role family
    assert not keeps("AI Engineer", "Sales Manager", AI_DESC)


def test_substring_lookalikes_do_not_count_as_ai():
    # the old matcher counted "ai" inside "maintain" / "email" / "detail"
    assert not keeps("AI Engineer", "Software Engineer", "maintain email detail daily retail mainframe " * 5)


# ---- rule 1: exact title outranks everything else --------------------------------------------
def test_ai_engineer_ranks_above_related_titles():
    jobs = [
        j("Machine Learning Engineer", source="career_page"),
        j("Applied AI Engineer", source="lever"),
        j("AI Engineer", source="indeed"),                 # worst source tier, still first
        j("Generative AI Engineer", source="greenhouse"),
    ]
    out = [x.title for x in sort_jobs(jobs, "priority", query="AI Engineer")]
    assert out[0] == "AI Engineer"
    assert out[-1] == "Machine Learning Engineer"          # related tier, below the AI-titled ones


def test_source_priority_still_orders_within_a_tier():
    jobs = [j("AI Engineer", source="indeed", company="B"), j("AI Engineer", source="career_page", company="A")]
    assert [x.source for x in sort_jobs(jobs, "priority", query="AI Engineer")] == ["career_page", "indeed"]


# ---- rule 3: related roles stay ---------------------------------------------------------------
def test_related_roles_are_kept():
    for t in ["Machine Learning Engineer", "ML Engineer", "Applied AI Engineer", "Generative AI Engineer",
              "GenAI Developer", "LLM Engineer", "Senior AI Engineer", "AI/ML Engineer", "AI Software Engineer",
              "Artificial Intelligence Engineer", "NLP Engineer"]:
        assert keeps("AI Engineer", t), t


def test_tiers():
    assert score_title("AI Engineer", "AI Engineer").tier == EXACT
    assert score_title("AI Engineer", "Machine Learning Engineer").tier == RELATED
    assert score_title("AI Engineer", "Senior AI Engineer").score >= score_title("AI Engineer", "Machine Learning Engineer").score


def test_machine_learning_query_also_finds_ai_titles_and_vice_versa():
    assert keeps("Machine Learning Engineer", "ML Engineer")
    assert keeps("Machine Learning Engineer", "AI Engineer")
    assert not keeps("Machine Learning Engineer", "Software Engineer", "machine learning machine learning")


# ---- other query shapes still behave ---------------------------------------------------------
def test_other_role_queries():
    assert keeps("python developer", "Python Engineer")
    assert keeps("python developer", "Backend Engineer", "We use Python and Django. Python everywhere.")   # skill: description ok
    assert not keeps("python developer", "Sales Manager", "Python")
    assert keeps("backend engineer", "Senior Backend Engineer")
    assert not keeps("backend engineer", "Frontend Engineer")
    assert not keeps("data scientist", "Data Engineer")
    assert keeps("data scientist", "Senior Data Scientist")
    assert not keeps("engineering manager", "Software Engineer")
    assert keeps("devops engineer", "Site Reliability Engineer")


def test_keyword_queries_use_title_or_description_whole_words():
    assert keeps("kubernetes", "Platform Engineer", "Run Kubernetes clusters")
    assert not keeps("kubernetes", "Platform Engineer", "Run clusters")
    assert score_title("python", "Python Developer").tier < score_title("python", "Backend Engineer", "Python").tier
    assert score_title("python", "Backend Engineer", "Python").tier == KEYWORD


def test_empty_query_keeps_everything_and_original_ordering():
    jobs = [j("A", source="indeed"), j("B", source="career_page")]
    assert keeps("", "Anything")
    assert [x.title for x in sort_jobs(jobs, "priority")] == ["B", "A"]


def test_applied_to_server_side_sources_too():
    # aggregators used to bypass the title check entirely (search_locally=False)
    assert not passes_filters(j("Software Engineer", AI_DESC), SearchFilters(q="AI Engineer"), search_locally=False)
