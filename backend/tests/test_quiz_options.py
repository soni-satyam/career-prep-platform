"""Quiz options: number of questions and question style (mix-up, interview, assessment, ...)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agents import quiz_agent
from app.agents.quiz_agent import (
    MAX_QUESTIONS,
    MIN_QUESTIONS,
    QUESTION_TYPE_IDS,
    QUESTION_TYPES,
    build_system_prompt,
    generate_quiz,
    min_acceptable,
    mix_plan,
)
from app.core import llm_cache, llm_router
from test_llm_router import ids, mk


def _quiz(n, tag="q", category="Concept"):
    return json.dumps(
        {
            "topic": "SQL",
            "questions": [
                {
                    "id": f"x{i}",
                    "category": category,
                    "question": f"{tag} question number {i}?",
                    "options": ["a1", "b2", "c3", "d4"],
                    "correct_index": i % 4,
                    "explanation": "because",
                }
                for i in range(n)
            ],
        }
    )


@pytest.fixture
def install(monkeypatch):
    monkeypatch.setattr(llm_router, "_router", None)

    def _install(*specs, **kw):
        llm_cache._mem.clear()
        router, calls, _ = mk(*specs, **kw)
        monkeypatch.setattr(llm_router, "_router", router)
        return calls

    return _install


# ----------------------------------------------------------------- the option list


def test_all_requested_styles_exist():
    assert set(QUESTION_TYPE_IDS) == {"mixed", "interview", "assessment", "most_asked", "conceptual", "practical", "coding"}
    for qt in QUESTION_TYPES.values():
        assert qt.label and qt.description and qt.guide and qt.tokens_per_question > 0


# ----------------------------------------------------------------- mix-up plan


@pytest.mark.parametrize("n", range(MIN_QUESTIONS, MAX_QUESTIONS + 1))
def test_mix_plan_always_sums_to_requested(n):
    plan = mix_plan(n)
    assert sum(plan.values()) == n
    if n >= 4:
        assert all(v >= 1 for v in plan.values())  # every kind appears


# ----------------------------------------------------------------- prompts


@pytest.mark.parametrize("qtype", QUESTION_TYPE_IDS)
def test_each_style_changes_the_prompt(qtype):
    prompt = build_system_prompt(qtype, 10)
    qt = QUESTION_TYPES[qtype]
    assert f"Question style: {qt.label}" in prompt
    assert qt.guide in prompt
    assert ("Use exactly this mix" in prompt) == (qtype == "mixed")


def test_prompts_differ_between_styles():
    prompts = {t: build_system_prompt(t, 10) for t in QUESTION_TYPE_IDS}
    assert len(set(prompts.values())) == len(QUESTION_TYPE_IDS)


def test_mixed_prompt_contains_the_exact_mix():
    p = build_system_prompt("mixed", 10)
    plan = mix_plan(10)
    assert ", ".join(f"{v} {k}" for k, v in plan.items()) in p


def test_style_specific_instructions():
    assert "online assessment" in build_system_prompt("assessment", 5)
    assert "easier to harder" in build_system_prompt("assessment", 5)
    assert "real interviewer" in build_system_prompt("interview", 5)
    assert "not live interview data" in build_system_prompt("most_asked", 5)
    assert "fenced block" in build_system_prompt("coding", 5)


def test_options_placeholder_does_not_invite_literal_letters():
    p = build_system_prompt("mixed", 5)
    assert '"A", "B"' not in p
    assert "Do not prefix options with letters" in p


# ----------------------------------------------------------------- generation


async def test_requested_count_and_style_reach_the_model(install):
    calls = install(dict(provider="groq", script=[_quiz(10)]))
    quiz = await generate_quiz("SQL", "hard", 10, question_type="interview")
    _, messages = calls[0]
    system, user = messages[0].content, messages[1].content
    assert "Number of questions: 10" in user and "Question style: Interview style" in user and "Difficulty: hard" in user
    assert "real interviewer" in system
    assert len(quiz["questions"]) == 10
    assert quiz["question_type"] == "interview" and quiz["num_requested"] == 10 and quiz["difficulty"] == "hard"


async def test_default_style_is_mixed_and_count_clamped(install):
    install(dict(provider="groq", script=[_quiz(20)]))
    q = await generate_quiz("SQL", "medium", 999)
    assert q["question_type"] == "mixed" and q["num_requested"] == MAX_QUESTIONS and len(q["questions"]) == MAX_QUESTIONS


async def test_unknown_style_falls_back_to_mixed(install):
    install(dict(provider="groq", script=[_quiz(5)]))
    assert (await generate_quiz("SQL", "easy", 5, question_type="nonsense"))["question_type"] == "mixed"


async def test_category_is_kept_and_extra_questions_trimmed(install):
    install(dict(provider="groq", script=[_quiz(8, category="Joins")]))
    quiz = await generate_quiz("SQL", "easy", 5, question_type="most_asked")
    assert len(quiz["questions"]) == 5
    assert {q["category"] for q in quiz["questions"]} == {"Joins"}
    assert [q["id"] for q in quiz["questions"]] == ["q1", "q2", "q3", "q4", "q5"]


async def test_duplicate_questions_are_removed(install):
    dup = json.dumps(
        {"questions": [{"question": "What is a JOIN?", "options": list("abcd"), "correct_index": 0, "explanation": ""}] * 4
         + [{"question": f"Different {i}?", "options": list("abcd"), "correct_index": 1, "explanation": ""} for i in range(4)]}
    )
    install(dict(provider="groq", script=[dup]))
    quiz = await generate_quiz("SQL", "easy", 5)
    texts = [q["question"] for q in quiz["questions"]]
    assert len(texts) == len(set(texts)) == 5


def test_minimum_acceptable_scales_with_size():
    assert min_acceptable(3) == 3 and min_acceptable(5) == 3 and min_acceptable(10) == 6 and min_acceptable(20) == 12


async def test_slightly_short_result_is_served_and_reported(install):
    calls = install(dict(provider="groq", script=[_quiz(14)]), dict(provider="gemini", script=[_quiz(20)]))
    quiz = await generate_quiz("SQL", "medium", 20)
    assert len(quiz["questions"]) == 14 and quiz["num_requested"] == 20  # UI shows "14 of 20"
    assert ids(calls) == ["groq:m"]                                      # no extra call burned


async def test_badly_short_result_fails_over_to_next_provider(install):
    calls = install(dict(provider="groq", script=[_quiz(4)]), dict(provider="gemini", script=[_quiz(20)]))
    quiz = await generate_quiz("SQL", "medium", 20)
    assert len(quiz["questions"]) == 20
    assert ids(calls) == ["groq:m", "gemini:m"]


async def test_large_coding_quiz_skips_groq_token_budget(install):
    """20 code questions ~7.3K tokens > Groq free plan's 8K/min budget (7000): go straight to the next entry."""
    calls = install(dict(provider="groq", tpm=7000), dict(provider="openrouter", script=[_quiz(20)]))
    await generate_quiz("Python", "medium", 20, question_type="coding")
    assert ids(calls) == ["openrouter:m"]


async def test_small_quiz_still_uses_primary(install):
    calls = install(dict(provider="groq", tpm=7000, script=[_quiz(5)]), dict(provider="openrouter"))
    await generate_quiz("Python", "medium", 5, question_type="assessment")
    assert ids(calls) == ["groq:m"]


async def test_new_quiz_with_same_settings_is_not_cached(install):
    calls = install(dict(provider="groq", script=[_quiz(5, "first"), _quiz(5, "second")]))
    a = await generate_quiz("SQL", "easy", 5, question_type="interview")
    b = await generate_quiz("SQL", "easy", 5, question_type="interview")
    assert a["questions"][0]["question"] != b["questions"][0]["question"] and len(calls) == 2


# ----------------------------------------------------------------- HTTP API validation


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api import quizzes
    from app.api.deps import get_current_user
    from app.main import app

    seen = {}

    async def fake_generate(**kwargs):
        seen.update(kwargs)
        return {"topic": kwargs["topic"], "questions": [], "question_type": kwargs["question_type"]}

    monkeypatch.setattr(quizzes, "generate_quiz", fake_generate)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="u1")
    yield TestClient(app), seen
    app.dependency_overrides.pop(get_current_user, None)


def post(client, **body):
    base = {"topic": "SQL"}
    return client.post("/api/v1/quizzes/generate", json={**base, **body})


def test_api_passes_count_and_style_through(client):
    c, seen = client
    r = post(c, num_questions=15, question_type="assessment", difficulty="hard")
    assert r.status_code == 200
    assert seen["num_questions"] == 15 and seen["question_type"] == "assessment" and seen["difficulty"] == "hard"


def test_api_defaults_are_backwards_compatible(client):
    c, seen = client
    assert post(c).status_code == 200
    assert seen["num_questions"] == 5 and seen["question_type"] == "mixed" and seen["difficulty"] == "medium"


@pytest.mark.parametrize("qtype", QUESTION_TYPE_IDS)
def test_api_accepts_every_style(client, qtype):
    c, seen = client
    assert post(c, question_type=qtype).status_code == 200 and seen["question_type"] == qtype


@pytest.mark.parametrize("body", [
    {"question_type": "trivia"}, {"num_questions": 2}, {"num_questions": 21}, {"num_questions": "ten"},
    {"difficulty": "impossible"}, {"topic": "x"},
])
def test_api_rejects_invalid_options(client, body):
    c, _ = client
    assert post(c, **body).status_code == 422


@pytest.mark.parametrize("n", [3, 20])
def test_api_count_bounds_are_inclusive(client, n):
    c, _ = client
    assert post(c, num_questions=n).status_code == 200
