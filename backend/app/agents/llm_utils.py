"""Shared helpers for agent LLM calls with JSON parsing."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Type, TypeVar

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.llm_cache import cached_call, make_key
from app.core.llm_router import get_router

T = TypeVar("T", bound=BaseModel)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def parse_json_response(content: str | Any) -> dict[str, Any]:
    if not isinstance(content, str):
        content = str(content)
    text = _strip_fences(content)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # try to find first { ... }
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {"raw_response": content, "error": "Failed to parse JSON"}


async def run_json_agent(
    system: str,
    user: str,
    schema: Type[T] | None = None,
    temperature: float = 0.2,
    *,
    cache_ttl: int = 0,
    dedupe: bool = False,
    validator: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    est_output_tokens: int = 1500,
) -> dict[str, Any]:
    """Call an LLM (via the provider router) and return parsed JSON.

    cache_ttl  > 0  -> identical (system, user, temperature) is served from cache.
    dedupe          -> identical requests running at the same moment share one call.
    validator       -> strict check of the parsed dict. If it raises, the router
                       fails over to the next provider instead of returning junk.
    est_output_tokens -> rough size of the answer; used for per-minute token budgets.

    Output that is not valid JSON always triggers failover. Output that is valid
    JSON but does not match `schema` is returned as-is (same lenient behaviour as
    before), because the schemas have defaults and another call would only burn quota.
    """
    settings = get_settings()

    def parse(text: str) -> dict[str, Any]:
        data = parse_json_response(text)
        if not isinstance(data, dict) or ("error" in data and "raw_response" in data):
            raise ValueError("model did not return a JSON object")
        if validator is not None:
            return validator(data)
        if schema is not None:
            try:
                return schema.model_validate(data).model_dump()
            except Exception:
                return data
        return data

    async def compute() -> dict[str, Any]:
        result, _provider = await get_router().complete(
            system,
            user,
            temperature=temperature,
            parse=parse,
            est_output_tokens=est_output_tokens,
        )
        return result

    ttl = cache_ttl if (cache_ttl > 0 and settings.llm_cache_enabled) else 0
    if ttl == 0 and not dedupe:
        return await compute()
    return await cached_call(
        make_key(system, user, temperature), compute, ttl=ttl, dedupe=True
    )
