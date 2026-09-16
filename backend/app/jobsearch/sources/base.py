from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.jobsearch.posting import JobPosting, SearchFilters


class SourceNotConfigured(Exception):
    """Raised by a source that needs an API key / board list that is not set."""


class TTLCache:
    def __init__(self, max_entries: int = 500) -> None:
        self._d: dict[str, tuple[float, Any]] = {}
        self._max = max_entries

    def get(self, key: str) -> Any:
        hit = self._d.get(key)
        if not hit:
            return None
        if hit[0] < time.monotonic():
            self._d.pop(key, None)
            return None
        return hit[1]

    def set(self, key: str, value: Any, ttl: float) -> None:
        if len(self._d) >= self._max:
            now = time.monotonic()
            for k in [k for k, (exp, _) in self._d.items() if exp < now]:
                self._d.pop(k, None)
            if len(self._d) >= self._max:
                self._d.pop(next(iter(self._d)), None)
        self._d[key] = (time.monotonic() + ttl, value)

    def clear(self) -> None:
        self._d.clear()


@dataclass
class SourceContext:
    client: httpx.AsyncClient
    cache: TTLCache
    cache_ttl: float = 600.0
    default_country: str = "in"


class JobSource:
    """One place jobs come from. Subclasses implement `fetch`."""

    name: str = "source"          # key shown in the API (e.g. "greenhouse")
    kind: str = "aggregator"      # ats | career_page | aggregator
    #: True when `fetch` already applies q/location server-side. ATS boards return everything
    #: and the service filters locally.
    server_side_search: bool = False

    def configured(self) -> bool:
        return True

    def not_configured_hint(self) -> str:
        return ""

    async def fetch(self, ctx: SourceContext, f: SearchFilters) -> list[JobPosting]:  # pragma: no cover
        raise NotImplementedError


# ------------------------------------------------------------------ helpers

def split_list(value: str | None) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def parse_dt(value: Any) -> Optional[datetime]:
    """ISO strings, epoch seconds or epoch milliseconds -> aware UTC datetime."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)):
            v = float(value)
            if v > 1e11:       # milliseconds
                v /= 1000.0
            return datetime.fromtimestamp(v, tz=timezone.utc)
        s = str(value).strip().replace("Z", "+00:00")
        if " " in s and "T" not in s:
            s = s.replace(" ", "T", 1)
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def annualize(amount: float | None, period: str | None) -> Optional[float]:
    if amount is None:
        return None
    p = (period or "year").lower()
    mult = 1.0
    if "month" in p:
        mult = 12.0
    elif "week" in p:
        mult = 52.0
    elif "day" in p:
        mult = 260.0
    elif "hour" in p:
        mult = 2080.0
    return float(amount) * mult


def title_case_slug(slug: str) -> str:
    return " ".join(w.capitalize() for w in slug.replace("_", "-").split("-"))
