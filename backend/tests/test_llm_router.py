"""Offline tests for the fallback chain, cache and agents (no network, no API keys).

Run:  cd backend && pip install pytest pytest-asyncio && pytest -q
"""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from app.core import llm_cache
from app.core.llm_router import (
    ChainEntry,
    LLMBusyError,
    LLMRouter,
    LLMUnavailableError,
    classify_error,
    estimate_tokens,
    parse_chain,
)

# ----------------------------------------------------------------- fakes


class Err(Exception):
    def __init__(self, msg="", status=None, headers=None):
        super().__init__(msg)
        self.status_code = status
        if headers:
            self.response = SimpleNamespace(status_code=status, headers=headers)


class FakeModel:
    def __init__(self, entry, script, calls):
        self.entry, self.script, self.calls = entry, script, calls

    async def ainvoke(self, messages):
        self.calls.append((self.entry.id, messages))
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        return SimpleNamespace(content=step, usage_metadata=None)


def mk(*specs, **router_kw):
    """mk(dict(provider=, model=, script=[...], rpm=, tpm=, shared=, merge=), ...)"""
    entries, scripts = [], {}
    for sp in specs:
        provider, model = sp["provider"], sp.get("model", "m")
        e = ChainEntry(
            provider=provider,
            model=model,
            kind="openai_compat",
            api_key="k",
            base_url=None,
            rpm=sp.get("rpm", 100),
            tpm=sp.get("tpm", 0),
            budget_key=provider if sp.get("shared") else f"{provider}:{model}",
            merge_system=sp.get("merge", False),
        )
        entries.append(e)
        scripts[e.id] = sp.get("script", ['{"ok":1}'])
    calls: list = []
    router = LLMRouter(
        entries,
        model_factory=lambda entry, t: FakeModel(entry, scripts[entry.id], calls),
        request_timeout=5,
        **router_kw,
    )
    return router, calls, [c[0] for c in calls]


def ids(calls):
    return [c[0] for c in calls]


async def run(router, system="s", user="u", **kw):
    return await router.complete(system, user, temperature=0.2, parse=json.loads, **kw)


# ----------------------------------------------------------------- chain order & budgets


async def test_primary_is_used_and_fallbacks_stay_idle():
    router, calls, _ = mk(
        dict(provider="groq", script=['{"p":"groq"}']),
        dict(provider="gemini", script=['{"p":"gemini"}']),
    )
    for _ in range(10):
        result, eid = await run(router)
        assert eid == "groq:m" and result == {"p": "groq"}
    assert "gemini:m" not in ids(calls)


async def test_spills_down_the_chain_and_never_exceeds_a_budget():
    """The original bug: more than N requests/min hammered a single provider."""
    router, calls, _ = mk(
        dict(provider="groq", rpm=3),
        dict(provider="openrouter", rpm=3),
        dict(provider="gemini", rpm=5),
    )
    used = [(await run(router))[1] for _ in range(8)]
    assert used == ["groq:m"] * 3 + ["openrouter:m"] * 3 + ["gemini:m"] * 2
    assert ids(calls).count("gemini:m") <= 5


async def test_openrouter_entries_share_one_account_budget():
    router, calls, _ = mk(
        dict(provider="openrouter", model="a", rpm=2, shared=True),
        dict(provider="openrouter", model="b", rpm=2, shared=True),
        dict(provider="gemini", rpm=10),
    )
    used = [(await run(router))[1] for _ in range(4)]
    assert used == ["openrouter:a", "openrouter:a", "gemini:m", "gemini:m"]
    assert "openrouter:b" not in ids(calls)  # same account => same 2/min budget


# ----------------------------------------------------------------- token budgets (Groq: 8K TPM)


async def test_request_bigger_than_tpm_skips_entry_without_calling_it():
    router, calls, _ = mk(
        dict(provider="groq", tpm=1000),
        dict(provider="gemini"),
    )
    big = "x" * 8000  # ~2300 tokens > 1000
    _, eid = await run(router, user=big)
    assert eid == "gemini:m"
    assert ids(calls) == ["gemini:m"]  # groq was never called


async def test_tpm_window_spills_to_next_then_recovers():
    router, calls, _ = mk(
        dict(provider="groq", tpm=2000),
        dict(provider="gemini"),
    )
    router._states[0].budget.window = 0.4  # shrink the minute so the test is quick
    user = "x" * 1700  # ~486 tokens + 1500 est output = 1986: nearly fills a 2000 budget alone
    assert (await run(router, user=user))[1] == "groq:m"
    assert (await run(router, user=user))[1] == "gemini:m"  # no budget left -> spill
    await asyncio.sleep(0.45)
    assert (await run(router, user=user))[1] == "groq:m"  # window passed -> primary again


# ----------------------------------------------------------------- failure types


async def test_429_fails_over_immediately_and_cools_entry_down():
    router, calls, _ = mk(
        dict(provider="groq", script=[Err("slow down", 429)]),
        dict(provider="gemini"),
    )
    assert (await run(router))[1] == "gemini:m"
    assert ids(calls) == ["groq:m", "gemini:m"]
    calls.clear()
    await run(router)
    assert ids(calls) == ["gemini:m"]  # groq is cooling: no wasted call
    row = router.status()[0]
    assert row["cooling_down_for_s"] > 0


async def test_retry_after_header_is_respected():
    router, _, _ = mk(
        dict(provider="groq", script=[Err("limit", 429, {"retry-after": "37"})]),
        dict(provider="gemini"),
    )
    await run(router)
    assert 30 < router.status()[0]["cooling_down_for_s"] <= 37


async def test_bad_key_disables_the_whole_provider_and_backs_off():
    router, calls, _ = mk(
        dict(provider="openrouter", model="a", script=[Err("No auth", 401)]),
        dict(provider="openrouter", model="b"),
        dict(provider="gemini"),
    )
    assert (await run(router))[1] == "gemini:m"
    assert ids(calls) == ["openrouter:a", "gemini:m"]  # model b skipped: same dead key
    row = router.status()[1]
    assert row["provider_disabled_for_s"] > 500
    assert row["provider_disabled_reason"] == "API key rejected"


async def test_out_of_credits_402_disables_provider_longer():
    router, _, _ = mk(
        dict(provider="huggingface", script=[Err("Payment Required", 402)]),
        dict(provider="gemini"),
    )
    await run(router)
    assert router.status()[0]["provider_disabled_for_s"] > 3000
    assert router.status()[0]["provider_disabled_reason"] == "out of credits"


async def test_invalid_request_is_not_retried_and_does_not_punish_provider():
    router, calls, _ = mk(
        dict(provider="groq", script=[Err("bad param", 400), '{"ok":1}']),
        dict(provider="gemini"),
    )
    assert (await run(router))[1] == "gemini:m"  # 400 -> next entry, never the same one again
    assert ids(calls).count("groq:m") == 1
    row = router.status()[0]
    assert row["cooling_down_for_s"] == 0 and row["parked_for_s"] == 0
    assert (await run(router))[1] == "groq:m"  # next request may use it again


async def test_entry_that_keeps_rejecting_requests_is_parked():
    router, calls, _ = mk(
        dict(provider="groq", script=[Err("unsupported", 400)]),
        dict(provider="gemini"),
    )
    for _ in range(3):
        await run(router)
    calls.clear()
    await run(router)
    assert ids(calls) == ["gemini:m"]
    assert router.status()[0]["parked_for_s"] > 500


async def test_413_too_large_has_no_penalty():
    router, _, _ = mk(
        dict(provider="groq", script=[Err("Request too large", 413)]),
        dict(provider="gemini"),
    )
    await run(router)
    row = router.status()[0]
    assert row["cooling_down_for_s"] == 0 and row["parked_for_s"] == 0


async def test_daily_quota_on_shared_account_parks_every_entry_of_that_provider():
    router, calls, _ = mk(
        dict(provider="openrouter", model="a", shared=True,
             script=[Err("Rate limit exceeded: free-models-per-day", 429)]),
        dict(provider="openrouter", model="b", shared=True),
        dict(provider="gemini"),
    )
    assert (await run(router))[1] == "gemini:m"
    assert ids(calls) == ["openrouter:a", "gemini:m"]  # b not wasted on the same dead quota
    assert router.status()[1]["cooling_down_for_s"] >= 3500


async def test_timeout_gets_short_cooldown_and_failover():
    router, _, _ = mk(
        dict(provider="groq", script=[asyncio.TimeoutError()]),
        dict(provider="gemini"),
    )
    assert (await run(router))[1] == "gemini:m"
    assert 0 < router.status()[0]["cooling_down_for_s"] <= 5


async def test_unusable_output_fails_over_without_repeating_same_entry():
    router, calls, _ = mk(
        dict(provider="groq", script=["not json at all"]),
        dict(provider="gemini"),
    )
    result, eid = await run(router)
    assert eid == "gemini:m" and result == {"ok": 1}
    assert ids(calls) == ["groq:m", "gemini:m"]


async def test_attempt_cap_keeps_fallback_small():
    router, calls, _ = mk(
        dict(provider="a", script=[Err("boom")]),
        dict(provider="b", script=[Err("boom")]),
        dict(provider="c", script=[Err("boom")]),
        max_attempts=2,
    )
    with pytest.raises(LLMUnavailableError):
        await run(router)
    assert len(calls) == 2


# ----------------------------------------------------------------- end of chain


async def test_busy_when_every_entry_is_at_budget():
    router, _, _ = mk(dict(provider="gemini", rpm=1), max_wait=0.2)
    await run(router)
    with pytest.raises(LLMBusyError) as ei:
        await run(router)
    assert ei.value.retry_after >= 1


async def test_waits_for_a_free_slot_when_it_is_short():
    router, _, _ = mk(dict(provider="gemini", rpm=1), max_wait=5)
    router._states[0].budget.window = 0.3
    await run(router)
    t0 = time.monotonic()
    await run(router)
    assert 0.2 < time.monotonic() - t0 < 2


async def test_all_providers_disabled_is_unavailable_not_busy():
    router, _, _ = mk(
        dict(provider="groq", script=[Err("bad key", 401)]),
        dict(provider="gemini", script=[Err("bad key", 401)]),
    )
    with pytest.raises(LLMUnavailableError):
        await run(router)
    with pytest.raises(LLMUnavailableError):  # and stays that way, with no new calls
        await run(router)


async def test_no_entries_configured():
    with pytest.raises(LLMUnavailableError):
        await run(LLMRouter([]))


async def test_request_too_large_for_every_entry_is_unavailable():
    router, calls, _ = mk(dict(provider="groq", tpm=100))
    with pytest.raises(LLMUnavailableError):
        await run(router, user="x" * 5000)
    assert calls == []


# ----------------------------------------------------------------- message shaping


async def test_system_prompt_is_folded_into_user_message_for_gemma_entries():
    router, calls, _ = mk(
        dict(provider="openrouter", model="google/gemma-4-31b-it:free", merge=True),
        dict(provider="groq"),
    )
    await run(router, system="SYSTEM RULES", user="USER TEXT")
    _, messages = calls[0]
    assert len(messages) == 1
    assert "SYSTEM RULES" in messages[0].content and "USER TEXT" in messages[0].content


async def test_normal_entries_keep_separate_system_message():
    router, calls, _ = mk(dict(provider="groq"))
    await run(router, system="SYS", user="USR")
    assert [m.type for m in calls[0][1]] == ["system", "human"]


# ----------------------------------------------------------------- classification


def test_classify_error():
    assert classify_error(Err("x", 429)) == "rate_limit"
    assert classify_error(Exception("429 RESOURCE_EXHAUSTED: quota exceeded")) == "rate_limit"
    assert classify_error(Exception("Resource has been exhausted (e.g. check quota).")) == "rate_limit"
    assert classify_error(Err("Payment Required", 402)) == "credits"
    assert classify_error(Err("x", 401)) == "auth"
    assert classify_error(Err("x", 403)) == "auth"
    assert classify_error(Err("400 API key not valid. Please pass a valid API key.", 400)) == "auth"
    assert classify_error(Err("x", 400)) == "bad_request"
    assert classify_error(Err("x", 422)) == "bad_request"
    assert classify_error(Err("x", 413)) == "too_large"
    assert classify_error(Err("x", 404)) == "bad_model"
    assert classify_error(Exception("model foo does not exist")) == "bad_model"
    assert classify_error(asyncio.TimeoutError()) == "timeout"
    assert classify_error(Err("Bad gateway", 502)) == "transient"
    assert classify_error(Exception("connection reset")) == "transient"


def test_estimate_tokens():
    assert estimate_tokens("a" * 350) == 100


# ----------------------------------------------------------------- chain parsing


def _settings(**kw):
    from app.core.config import Settings

    return Settings(_env_file=None, **kw)


def test_default_chain_is_the_requested_one_and_skips_keyless_entries():
    s = _settings(groq_api_key="g", google_api_key="AIzaX")
    entries, skipped = parse_chain(s)
    assert [e.id for e in entries] == ["groq:openai/gpt-oss-20b", "gemini:gemini-3.5-flash-lite"]
    assert any("openrouter:google/gemma-4-31b-it:free" in x for x in skipped)
    assert any("huggingface:openai/gpt-oss-20b" in x for x in skipped)


def test_full_chain_order_and_per_entry_settings():
    s = _settings(groq_api_key="g", openrouter_api_key="o", google_api_key="a", huggingface_api_key="h")
    entries, skipped = parse_chain(s)
    assert [e.id for e in entries] == [
        "groq:openai/gpt-oss-20b",
        "openrouter:google/gemma-4-31b-it:free",       # ':free' suffix kept in the model name
        "openrouter:google/gemma-4-26b-a4b-it:free",
        "gemini:gemini-3.5-flash-lite",
        "huggingface:openai/gpt-oss-20b",              # last resort
    ]
    assert skipped == []
    groq, or1, or2, gem, hf = entries
    assert groq.tpm == 7000 and groq.json_mode and groq.extra_body == {"reasoning_effort": "low"}
    assert or1.merge_system and or2.merge_system          # Gemma
    assert or1.budget_key == or2.budget_key == "openrouter"  # account-wide budget
    assert hf.budget_key == "huggingface" and hf.extra_body == {"reasoning_effort": "low"}
    assert gem.rpm == 5 and gem.kind == "gemini"
    assert not groq.merge_system and not gem.merge_system


def test_hugging_face_key_accepts_hf_token_env(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_abcdefghijk")
    s = _settings()
    assert s.huggingface_api_key == "hf_abcdefghijk"


def test_custom_chain_and_bad_entries():
    s = _settings(
        groq_api_key="g",
        llm_chain="groq:llama-3.3-70b-versatile, nonsense, bogus:model, groq:llama-3.3-70b-versatile",
    )
    entries, _ = parse_chain(s)
    assert [e.id for e in entries] == ["groq:llama-3.3-70b-versatile"]  # dupes/invalid dropped
    assert entries[0].extra_body is None                                 # reasoning_effort only for gpt-oss


# ----------------------------------------------------------------- cache / dedupe


async def test_dedupe_shares_one_call():
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return {"v": calls}

    key = llm_cache.make_key("s", "dedupe-test", 0.4)
    results = await asyncio.gather(*(llm_cache.cached_call(key, compute, ttl=0) for _ in range(5)))
    assert calls == 1 and all(r == {"v": 1} for r in results)
    await llm_cache.cached_call(key, compute, ttl=0)  # ttl=0: not cached afterwards
    assert calls == 2


async def test_cache_hit_skips_call_and_returns_copy():
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        return {"x": [1, 2]}

    key = llm_cache.make_key("s", "cache-test", 0.2)
    a = await llm_cache.cached_call(key, compute, ttl=60)
    b = await llm_cache.cached_call(key, compute, ttl=60)
    assert calls == 1 and a == b
    b["x"].append(3)
    assert (await llm_cache.cached_call(key, compute, ttl=60)) == {"x": [1, 2]}


async def test_dedupe_propagates_errors_to_all_waiters():
    async def compute():
        await asyncio.sleep(0.02)
        raise RuntimeError("provider down")

    key = llm_cache.make_key("s", "err-test", 0.2)
    res = await asyncio.gather(
        *(llm_cache.cached_call(key, compute, ttl=0) for _ in range(3)), return_exceptions=True
    )
    assert all(isinstance(r, RuntimeError) for r in res)


# ----------------------------------------------------------------- agents (fake router)


@pytest.fixture
def fake_router(monkeypatch):
    from app.core import llm_router

    monkeypatch.setattr(llm_router, "_router", None)

    def install(*specs, **kw):
        llm_cache._mem.clear()  # tests must not see each other's cached answers
        router, calls, _ = mk(*specs, **kw)
        monkeypatch.setattr(llm_router, "_router", router)
        return calls

    return install


def _quiz(tag, n=5):
    return json.dumps(
        {"questions": [{"id": f"q{i}", "question": f"{tag}{i}?", "options": list("ABCD"),
                        "correct_index": i % 4, "explanation": "e"} for i in range(n)]}
    )


async def test_quiz_malformed_output_fails_over_instead_of_empty_quiz(fake_router):
    from app.agents.quiz_agent import generate_quiz

    bad = json.dumps({"questions": [{"question": "q", "options": ["a", "b"], "correct_index": 9}]})
    calls = fake_router(dict(provider="groq", script=[bad]), dict(provider="gemini", script=[_quiz("g")]))
    quiz = await generate_quiz("SQL", "medium", 5)
    assert len(quiz["questions"]) == 5
    assert ids(calls) == ["groq:m", "gemini:m"]


async def test_quiz_new_quiz_is_not_cached(fake_router):
    from app.agents.quiz_agent import generate_quiz

    calls = fake_router(dict(provider="groq", script=[_quiz("first"), _quiz("second")]))
    a = await generate_quiz("Python", "easy", 5)
    b = await generate_quiz("Python", "easy", 5)
    assert a["questions"][0]["question"] != b["questions"][0]["question"]
    assert len(calls) == 2


async def test_pipeline_modes_call_counts(fake_router):
    from app.agents.orchestrator import run_full_pipeline

    generic = json.dumps({"title": "Engineer", "preparation_plan": [], "resume_tips": ["t"],
                          "interview_qa": [], "gaps": []})
    jd, resume = "J" * 120, "R" * 300

    async def count(mode, with_resume=True):
        calls = fake_router(dict(provider="groq", script=[generic]))
        await run_full_pipeline(jd, resume if with_resume else "", mode=mode)
        return len(calls)

    assert await count("full") == 6
    assert await count("resume") == 5
    assert await count("interview") == 3
    assert await count("interview", with_resume=False) == 2


async def test_analysis_agents_are_cached_across_pages(fake_router):
    from app.agents.orchestrator import run_full_pipeline

    generic = json.dumps({"title": "Engineer", "preparation_plan": [], "resume_tips": [],
                          "interview_qa": [], "gaps": []})
    jd, resume = "same jd text " * 20, "same resume text " * 30
    calls = fake_router(dict(provider="groq", script=[generic]))
    await run_full_pipeline(jd, resume, mode="resume")      # jd, profile, gap, resume, plan
    first = len(calls)
    await run_full_pipeline(jd, resume, mode="interview")   # jd + profile cached -> only interview
    assert first == 5 and len(calls) - first == 1


# ----------------------------------------------------------------- user-facing errors


def test_error_messages_for_users():
    from app.core.errors import llm_http_error, public_detail

    status, detail = llm_http_error(LLMBusyError(12.2))
    assert status == 429 and "13 seconds" in public_detail(status, detail)
    status, detail = llm_http_error(LLMUnavailableError("all failed: groq 401"))
    assert status == 503
    assert "groq" not in public_detail(status, detail).lower()  # internals never leak
