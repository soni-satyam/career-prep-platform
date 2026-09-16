"""Result cache + in-flight de-duplication for LLM calls.

* `ttl > 0`  -> identical prompts are served from cache (Redis, falling back to
               process memory if Redis is unavailable).
* `dedupe`   -> if the same prompt is already running (double click, React
               StrictMode, two tabs), the second caller awaits the first
               instead of making another LLM call.

Only ever used for requests where "same input -> same answer" is acceptable.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger("careerprep.llm")

_KEY_PREFIX = "llm:v1:"
_MEM_MAX = 512

_mem: dict[str, tuple[float, str]] = {}
_inflight: dict[str, "asyncio.Future[Any]"] = {}


def make_key(system: str, user: str, temperature: float) -> str:
    raw = json.dumps([system, user, round(temperature, 2)], ensure_ascii=False)
    return _KEY_PREFIX + hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _redis_get(key: str) -> Optional[str]:
    try:
        from app.core.redis import get_redis

        return await (await get_redis()).get(key)
    except Exception:  # Redis down -> memory only
        return None


async def _redis_set(key: str, value: str, ttl: int) -> None:
    try:
        from app.core.redis import get_redis

        await (await get_redis()).set(key, value, ex=ttl)
    except Exception:
        pass


async def cache_get(key: str) -> Optional[Any]:
    now = time.time()
    hit = _mem.get(key)
    if hit and hit[0] > now:
        return json.loads(hit[1])
    raw = await _redis_get(key)
    if raw:
        return json.loads(raw)
    return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    raw = json.dumps(value, ensure_ascii=False)
    if len(_mem) >= _MEM_MAX:
        now = time.time()
        for k in [k for k, (exp, _) in _mem.items() if exp <= now] or list(_mem)[: _MEM_MAX // 4]:
            _mem.pop(k, None)
    _mem[key] = (time.time() + ttl, raw)
    await _redis_set(key, raw, ttl)


async def cached_call(
    key: str,
    compute: Callable[[], Awaitable[Any]],
    *,
    ttl: int = 0,
    dedupe: bool = True,
) -> Any:
    """Return the cached value, else share an in-flight call, else compute."""
    if ttl > 0:
        hit = await cache_get(key)
        if hit is not None:
            logger.info("llm cache hit")
            return hit

    if dedupe:
        running = _inflight.get(key)
        if running is not None:
            logger.info("llm call de-duplicated (joined in-flight request)")
            # shield: if the joiner is cancelled, the original call keeps going
            return json.loads(await asyncio.shield(running))

        fut: "asyncio.Future[str]" = asyncio.get_running_loop().create_future()
        _inflight[key] = fut
        try:
            value = await compute()
            serialised = json.dumps(value, ensure_ascii=False)
            if ttl > 0:
                await cache_set(key, value, ttl)
            fut.set_result(serialised)
            return value
        except asyncio.CancelledError:
            fut.cancel()
            raise
        except Exception as exc:
            fut.set_exception(exc)
            fut.exception()  # mark retrieved so asyncio doesn't warn when nobody joined
            raise
        finally:
            _inflight.pop(key, None)

    value = await compute()
    if ttl > 0:
        await cache_set(key, value, ttl)
    return value
