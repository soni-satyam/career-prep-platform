"""Runs the REAL langchain-openai client (the one used for Groq / OpenRouter /
Hugging Face) against a local fake OpenAI-compatible server. No internet, no keys.

It checks the request we actually put on the wire (reasoning_effort, JSON mode,
folded system prompt) and that real SDK errors (429/402/401/400/413/404) are
classified and handled by the router as designed.
"""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.llm_router import ChainEntry, LLMRouter, default_model_factory

SEEN: list[dict] = []


def _completion(content: str):
    return {
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 40, "completion_tokens": 10, "total_tokens": 50},
    }


def build_app():
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        SEEN.append(body)
        model = body["model"]
        err = lambda status, msg, **h: JSONResponse(  # noqa: E731
            {"error": {"message": msg, "type": "x"}}, status_code=status, headers=h)
        if model == "rate":
            return err(429, "Rate limit reached for requests per minute", **{"Retry-After": "7"})
        if model == "daily":
            return err(429, "Rate limit exceeded: free-models-per-day")
        if model == "pay":
            return err(402, "Payment Required: you have exceeded your monthly included credits")
        if model == "auth":
            return err(401, "Invalid API Key")
        if model == "bad":
            return err(400, "Unsupported parameter")
        if model == "big":
            return err(413, "Request too large for model on tokens per minute (TPM): Limit 8000")
        if model == "missing":
            return err(404, "The model `missing` does not exist")
        if model == "boom":
            return err(503, "Service unavailable")
        if model == "prose":
            return JSONResponse(_completion("Sure! Here you go, no JSON."))
        return JSONResponse(_completion('{"answer": 42}'))

    return app


@pytest.fixture(scope="module")
def base_url():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(build_app(), host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1"
    server.should_exit = True
    t.join(timeout=5)


def entry(base_url, provider, model, **kw):
    return ChainEntry(
        provider=provider, model=model, kind="openai_compat", api_key="k", base_url=base_url,
        rpm=100, tpm=kw.pop("tpm", 0), budget_key=provider if kw.pop("shared", False) else f"{provider}:{model}",
        **kw,
    )


def router_for(*entries, **kw):
    return LLMRouter(list(entries), model_factory=default_model_factory, request_timeout=10, **kw)


async def run(router, **kw):
    return await router.complete("SYSTEM RULES", "USER TEXT", temperature=0.2, parse=json.loads, **kw)


async def test_wire_format_groq_style(base_url):
    SEEN.clear()
    r = router_for(entry(base_url, "groq", "ok", extra_body={"reasoning_effort": "low"}, json_mode=True))
    result, eid = await run(r)
    assert result == {"answer": 42}
    body = SEEN[-1]
    assert body["reasoning_effort"] == "low"                       # sent via extra_body
    assert body["response_format"] == {"type": "json_object"}      # JSON mode
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


async def test_wire_format_gemma_folds_system_prompt(base_url):
    SEEN.clear()
    r = router_for(entry(base_url, "openrouter", "ok", merge_system=True))
    await run(r)
    msgs = SEEN[-1]["messages"]
    assert [m["role"] for m in msgs] == ["user"]
    assert "SYSTEM RULES" in msgs[0]["content"] and "USER TEXT" in msgs[0]["content"]
    assert "reasoning_effort" not in SEEN[-1] and "response_format" not in SEEN[-1]


async def test_no_hidden_sdk_retries_on_429(base_url):
    """One logical request must be exactly one HTTP call per entry tried."""
    SEEN.clear()
    r = router_for(entry(base_url, "groq", "rate"), entry(base_url, "gemini", "ok"))
    _, eid = await run(r)
    assert eid == "gemini:ok"
    assert [b["model"] for b in SEEN] == ["rate", "ok"]  # not rate, rate, rate, ...


async def test_real_429_retry_after_and_real_error_types(base_url):
    r = router_for(entry(base_url, "groq", "rate"), entry(base_url, "gemini", "ok"))
    await run(r)
    assert 5 < r.status()[0]["cooling_down_for_s"] <= 7


async def test_real_402_disables_huggingface(base_url):
    r = router_for(entry(base_url, "huggingface", "pay"), entry(base_url, "gemini", "ok"))
    await run(r)
    row = r.status()[0]
    assert row["provider_disabled_reason"] == "out of credits"
    assert row["provider_disabled_for_s"] > 3000


async def test_real_401_disables_provider(base_url):
    r = router_for(entry(base_url, "openrouter", "auth"), entry(base_url, "gemini", "ok"))
    await run(r)
    assert r.status()[0]["provider_disabled_reason"] == "API key rejected"


async def test_real_400_is_not_retried_and_next_entry_serves(base_url):
    SEEN.clear()
    r = router_for(entry(base_url, "groq", "bad"), entry(base_url, "gemini", "ok"))
    _, eid = await run(r)
    assert eid == "gemini:ok"
    assert [b["model"] for b in SEEN] == ["bad", "ok"]
    assert r.status()[0]["cooling_down_for_s"] == 0


async def test_real_413_and_404_and_503(base_url):
    r = router_for(
        entry(base_url, "groq", "big"),
        entry(base_url, "openrouter", "missing"),
        entry(base_url, "cerebras", "boom"),
        entry(base_url, "gemini", "ok"),
        max_attempts=5,
    )
    _, eid = await run(r)
    assert eid == "gemini:ok"
    rows = {row["entry"]: row for row in r.status()}
    assert rows["groq:big"]["cooling_down_for_s"] == 0 and rows["groq:big"]["parked_for_s"] == 0  # too large: no penalty
    assert rows["openrouter:missing"]["parked_for_s"] > 800                                        # bad model: parked
    assert 0 < rows["cerebras:boom"]["cooling_down_for_s"] <= 5                                     # 5xx: short cooldown


async def test_daily_limit_parks_all_shared_entries(base_url):
    SEEN.clear()
    r = router_for(
        entry(base_url, "openrouter", "daily", shared=True),
        entry(base_url, "openrouter", "ok", shared=True),
        entry(base_url, "gemini", "ok"),
    )
    _, eid = await run(r)
    assert eid == "gemini:ok"
    assert [b["model"] for b in SEEN] == ["daily", "ok"]  # 2nd openrouter entry never called (gemini is "ok")
    rows = {row["entry"]: row for row in r.status()}
    assert rows["openrouter:ok"]["cooling_down_for_s"] >= 3500


async def test_non_json_prose_fails_over(base_url):
    r = router_for(entry(base_url, "groq", "prose"), entry(base_url, "gemini", "ok"))
    result, eid = await run(r)
    assert eid == "gemini:ok" and result == {"answer": 42}


async def test_real_token_usage_corrects_the_estimate(base_url):
    r = router_for(entry(base_url, "groq", "ok", tpm=7000))
    await run(r, est_output_tokens=3000)
    _, tokens = r._states[0].budget.used(time.monotonic())
    assert tokens == 50  # server reported 50 actual tokens, not the ~3000 estimate
