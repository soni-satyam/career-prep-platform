"""PART 7c - Tiny in-memory sliding-window limiter, keyed by client IP.
Protects your free LLM quota from abuse. (Behind a proxy, IPs may all look the same -
configure uvicorn --proxy-headers when you deploy.)"""
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request

from app import config


class RateLimiter:
    def __init__(self, max_calls_getter, window_seconds: int = 3600):
        self._max = max_calls_getter
        self._window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self._window:
                q.popleft()
            if len(q) >= self._max():
                return False
            q.append(now)
            if len(self._hits) > 10_000:                # keep memory bounded
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return True


session_limiter = RateLimiter(lambda: config.RATE_LIMIT_SESSIONS_PER_HOUR)
practice_limiter = RateLimiter(lambda: config.RATE_LIMIT_PRACTICE_PER_HOUR)


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def limit_sessions(request: Request) -> None:
    if not session_limiter.allow(_client(request)):
        raise HTTPException(429, "Too many prep sessions from your address. Try again later.")


def limit_practice(request: Request) -> None:
    if not practice_limiter.allow(_client(request)):
        raise HTTPException(429, "Too many practice submissions. Try again later.")
