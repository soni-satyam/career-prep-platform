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
    MAX_BATCH,
    MAX_TOPUP_ROUNDS,
    build_system_prompt,
    generate_quiz,
    mix_plan,
    plan_batches,
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


# ----------------------------------------------------------------- batching plan


@pytest.mark.parametrize("n", range(MIN_QUESTIONS, MAX_QUESTIONS + 1))
def test_batches_sum_to_n_and_stay_small(n):
    sizes = plan_batches(n)
    assert sum(sizes) == n and max(sizes) <= MAX_BATCH and max(sizes) - min(sizes) <= 1


def test_batch_plan_examples():
    assert plan_batches(5) == [5] and plan_batches(10) == [10]
    assert plan_batches(15) == [8, 7] and plan_batches(20) == [10, 10]


# ----------------------------------------------------------------- helpers for generation tests


def _distinct(start, n, category="Concept"):
    """n well-formed questions that are all different from each other (and from other `start` ranges)."""
    return json.dumps(
        {
            "topic": "SQL",
            "questions": [
                {
                    "category": category,
                    "question": f"Explain scenario number {start + i} involving {['joins','indexes','locks','views'][(start + i) % 4]}?",
                    "options": [f"alpha {start + i}", f"beta {start + i}", "gamma", "delta"],
                    "correct_index": (start + i) % 4,
                    "explanation": "because",
                }
                for i in range(n)
            ],
        }
    )


def _user_msgs(calls):
    return [c[1][-1].content for c in calls]


def _sys_msgs(calls):
    return [c[1][0].content for c in calls if len(c[1]) > 1]


# ----------------------------------------------------------------- generation


async def test_requested_count_and_style_reach_the_model(install):
    calls = install(dict(provider="groq", script=[_distinct(0, 10)]))
    quiz = await generate_quiz("SQL", "hard", 10, question_type="interview")
    user, system = _user_msgs(calls)[0], _sys_msgs(calls)[0]
    assert "Number of questions: 10" in user and "Question style: Interview style" in user and "Difficulty: hard" in user
    assert 'must contain exactly 10 items' in user and "exactly 10 items" in system
    assert "real interviewer" in system
    assert len(quiz["questions"]) == 10
    assert quiz["question_type"] == "interview" and quiz["num_requested"] == 10 and quiz["difficulty"] == "hard"


async def test_exact_count_costs_exactly_one_call(install):
    calls = install(dict(provider="groq", script=[_distinct(0, 10)]))
    await generate_quiz("SQL", "medium", 10)
    assert len(calls) == 1


async def test_default_style_is_mixed_and_count_clamped(install):
    install(dict(provider="groq", script=[_distinct(0, 10), _distinct(10, 10)]))
    q = await generate_quiz("SQL", "medium", 999)
    assert q["question_type"] == "mixed" and q["num_requested"] == MAX_QUESTIONS and len(q["questions"]) == MAX_QUESTIONS


async def test_unknown_style_falls_back_to_mixed(install):
    install(dict(provider="groq", script=[_distinct(0, 5)]))
    assert (await generate_quiz("SQL", "easy", 5, question_type="nonsense"))["question_type"] == "mixed"


async def test_category_is_kept_extras_trimmed_and_ids_renumbered(install):
    install(dict(provider="groq", script=[_distinct(0, 8, category="Joins")]))
    quiz = await generate_quiz("SQL", "easy", 5, question_type="most_asked")
    assert len(quiz["questions"]) == 5
    assert {q["category"] for q in quiz["questions"]} == {"Joins"}
    assert [q["id"] for q in quiz["questions"]] == ["q1", "q2", "q3", "q4", "q5"]


async def test_new_quiz_with_same_settings_is_not_cached(install):
    calls = install(dict(provider="groq", script=[_distinct(0, 5), _distinct(100, 5)]))
    a = await generate_quiz("SQL", "easy", 5, question_type="interview")
    b = await generate_quiz("SQL", "easy", 5, question_type="interview")
    assert a["questions"][0]["question"] != b["questions"][0]["question"] and len(calls) == 2


# ----------------------------------------------------------------- the count is guaranteed


@pytest.mark.parametrize("first,wanted", [(7, 10), (5, 10), (1, 5), (14, 20)])
async def test_short_answer_is_topped_up_to_the_requested_count(install, first, wanted):
    """The reported bug: asked for N, the model returned fewer, and the user got fewer."""
    sizes = plan_batches(wanted)
    script = [_distinct(0, first if len(sizes) == 1 else min(first // len(sizes), sizes[0])), _distinct(500, 10), _distinct(900, 10)]
    install(dict(provider="groq", script=script, rpm=100))
    quiz = await generate_quiz("SQL", "medium", wanted)
    assert len(quiz["questions"]) == wanted
    texts = [q["question"] for q in quiz["questions"]]
    assert len(set(texts)) == wanted


async def test_top_up_tells_the_model_what_already_exists_and_asks_only_for_the_rest(install):
    calls = install(dict(provider="groq", script=[_distinct(0, 7), _distinct(100, 10)], rpm=100))
    await generate_quiz("SQL", "medium", 10)
    first, second = _user_msgs(calls)
    assert "already exist" not in first
    assert "Number of questions: 3" in second          # only the missing three
    assert "Do NOT repeat" in second and "scenario number 0" in second  # lists what exists


async def test_top_up_is_bounded(install):
    calls = install(dict(provider="groq", script=[_distinct(0, 4), _distinct(100, 4), _distinct(200, 4), _distinct(300, 4)], rpm=100))
    quiz = await generate_quiz("SQL", "medium", 10)
    assert len(calls) == 1 + MAX_TOPUP_ROUNDS            # never loops forever
    assert len(quiz["questions"]) == 10                  # 4 + 4 + 4 = 12 distinct, trimmed to the 10 asked for
    assert quiz["num_requested"] == 10


async def test_provider_that_cannot_fill_the_quiz_is_reported_not_hidden(install):
    install(dict(provider="groq", script=[_distinct(0, 4)], rpm=100))  # repeats the same 4 every call
    quiz = await generate_quiz("SQL", "medium", 10)
    assert len(quiz["questions"]) == 4 and quiz["num_requested"] == 10   # UI shows "4 of 10"


async def test_failed_top_up_keeps_the_good_questions(install):
    from test_llm_router import Err

    calls = install(
        dict(provider="groq", script=[_distinct(0, 7), Err("boom", 400)], rpm=100),
    )
    quiz = await generate_quiz("SQL", "medium", 10)
    assert len(quiz["questions"]) == 7                    # not an error page


async def test_all_batches_failing_raises(install):
    from test_llm_router import Err

    install(dict(provider="groq", script=[Err("down", 401)], rpm=100))
    with pytest.raises(Exception):
        await generate_quiz("SQL", "medium", 10)


async def test_garbage_output_fails_over_to_next_provider(install):
    bad = json.dumps({"questions": [{"question": "q", "options": ["a", "b"], "correct_index": 9}]})
    calls = install(dict(provider="groq", script=[bad]), dict(provider="gemini", script=[_distinct(0, 5)]))
    quiz = await generate_quiz("SQL", "medium", 5)
    assert len(quiz["questions"]) == 5 and ids(calls) == ["groq:m", "gemini:m"]


# ----------------------------------------------------------------- big quizzes are written in parallel batches


async def test_twenty_questions_are_two_batches_of_ten(install):
    calls = install(dict(provider="groq", script=[_distinct(0, 10), _distinct(100, 10)], rpm=100))
    quiz = await generate_quiz("SQL", "medium", 20, question_type="interview")
    assert len(calls) == 2 and len(quiz["questions"]) == 20
    users = _user_msgs(calls)
    assert all("Number of questions: 10" in u for u in users)
    systems = _sys_msgs(calls)
    assert any("part 1 of 2" in s for s in systems) and any("part 2 of 2" in s for s in systems)


async def test_fifteen_questions_are_batches_of_eight_and_seven(install):
    calls = install(dict(provider="groq", script=[_distinct(0, 8), _distinct(100, 7)], rpm=100))
    quiz = await generate_quiz("SQL", "medium", 15)
    sizes = sorted(int(u.split("Number of questions: ")[1].split(" ")[0]) for u in _user_msgs(calls))
    assert sizes == [7, 8] and len(quiz["questions"]) == 15


async def test_assessment_parts_are_easier_then_harder(install):
    calls = install(dict(provider="groq", script=[_distinct(0, 10), _distinct(100, 10)], rpm=100))
    await generate_quiz("SQL", "medium", 20, question_type="assessment")
    joined = " ".join(_sys_msgs(calls))
    assert "easier half" in joined and "harder half" in joined


async def test_mixed_batches_each_get_their_own_exact_mix(install):
    calls = install(dict(provider="groq", script=[_distinct(0, 10), _distinct(100, 10)], rpm=100))
    await generate_quiz("SQL", "medium", 20, question_type="mixed")
    expected = ", ".join(f"{v} {k}" for k, v in mix_plan(10).items())
    assert all(expected in s for s in _sys_msgs(calls))


async def test_one_failed_batch_is_recovered_by_top_up(install):
    from test_llm_router import Err

    calls = install(dict(provider="groq", script=[_distinct(0, 10), Err("bad", 400), _distinct(100, 10)], rpm=100))
    quiz = await generate_quiz("SQL", "medium", 20)
    assert len(quiz["questions"]) == 20


# ----------------------------------------------------------------- duplicate handling


async def test_identical_questions_from_two_batches_are_removed(install):
    same = _distinct(0, 10)
    install(dict(provider="groq", script=[same, same, _distinct(100, 10)], rpm=100))
    quiz = await generate_quiz("SQL", "medium", 20)
    texts = [q["question"] for q in quiz["questions"]]
    assert len(texts) == len(set(texts)) == 20


_LONG = ("Consider a table named employees that has one thousand rows and an index on the salary column. "
         "How many rows does a query using LIMIT {k} return when no filtering clause is applied at all?")


def _sim(k, correct, **extra):
    return {"question": _LONG.format(k=k), "options": [str(correct), "none", "all rows", "an error"], "correct_index": 0,
            "explanation": "", **extra}


def test_regression_guard_questions_really_are_over_the_similarity_threshold():
    """Keeps the two tests below honest: the wording alone WOULD be flagged as a duplicate."""
    from app.agents.quiz_agent import _jaccard, _tokens

    assert _jaccard(_tokens(_LONG.format(k=5)), _tokens(_LONG.format(k=6))) >= 0.85


async def test_questions_identical_except_for_a_number_are_kept_when_answers_differ(install):
    """Code/aptitude questions ('LIMIT 5' vs 'LIMIT 6'): near-identical wording, different answers."""
    qs = [_sim(k, k) for k in range(5, 10)]
    install(dict(provider="groq", script=[json.dumps({"questions": qs})]))
    quiz = await generate_quiz("SQL", "easy", 5)
    assert len(quiz["questions"]) == 5


async def test_near_identical_questions_with_the_same_answer_are_duplicates(install):
    """Same question reworded by a second batch: near-identical wording AND the same answer."""
    base = _sim(5, 5)
    reworded = {**base, "question": base["question"].replace("table", "relation")}
    others = [{"question": f"Unrelated question {i} about transactions and isolation?", "options": [f"x{i}", "y", "z", "w"],
               "correct_index": 0, "explanation": ""} for i in range(4)]
    install(dict(provider="groq", script=[json.dumps({"questions": [base, reworded] + others})]))
    quiz = await generate_quiz("SQL", "easy", 5)
    assert sum("employees" in q["question"] or "relation" in q["question"] for q in quiz["questions"]) == 1


async def test_reworded_duplicate_with_same_answer_is_removed(install):
    base = {"question": "What is the purpose of a primary key in a relational table?", "options": ["Uniquely identify rows", "b", "c", "d"], "correct_index": 0, "explanation": ""}
    near = {**base, "question": "What is the purpose of a primary key in a relational table"}  # same words
    other = [{"question": f"Different question {i} about transactions?", "options": [f"x{i}", "y", "z", "w"], "correct_index": 0, "explanation": ""} for i in range(4)]
    install(dict(provider="groq", script=[json.dumps({"questions": [base, near] + other})]))
    quiz = await generate_quiz("SQL", "easy", 5)
    texts = [q["question"] for q in quiz["questions"]]
    assert sum("primary key" in t for t in texts) == 1


# ----------------------------------------------------------------- token budgets (Groq free plan: 8K tokens/min)


async def test_second_big_batch_spills_to_next_provider_when_groq_budget_is_used(install):
    """20 questions = 2 x ~4K tokens. Only one fits Groq's 7000/min budget; the other goes to the next entry."""
    calls = install(
        dict(provider="groq", tpm=7000, script=[_distinct(0, 10)]),
        dict(provider="openrouter", script=[_distinct(100, 10)]),
    )
    quiz = await generate_quiz("Python", "medium", 20, question_type="coding")
    assert sorted(ids(calls)) == ["groq:m", "openrouter:m"] and len(quiz["questions"]) == 20


async def test_small_quiz_still_uses_primary(install):
    calls = install(dict(provider="groq", tpm=7000, script=[_distinct(0, 5)]), dict(provider="openrouter"))
    await generate_quiz("Python", "medium", 5, question_type="assessment")
    assert ids(calls) == ["groq:m"]


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
