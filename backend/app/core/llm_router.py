"""LLM router: an ordered fallback chain of (provider, model) entries.

Default chain (see LLM_CHAIN in .env):
    1. groq        openai/gpt-oss-20b
    2. openrouter  google/gemma-4-31b-it:free
    3. openrouter  google/gemma-4-26b-a4b-it:free
    4. gemini      gemini-3.5-flash-lite
    5. huggingface openai/gpt-oss-20b          (tiny $0.10/month credit: last resort)
    6. nothing left -> LLMBusyError / LLMUnavailableError (clear message to the user)

For every request the router walks the chain top to bottom and:

* skips entries whose provider has no key (or whose key was rejected recently),
* skips entries that are cooling down after a 429 / outage,
* skips entries that have used their own requests-per-minute or tokens-per-minute
  budget, so it never *sends* a call that is certain to be rejected,
* on failure moves to the next entry instead of retrying the same one,
* stops after LLM_MAX_ATTEMPTS real calls (small, bounded fallback),
* treats unusable output (not JSON / wrong quiz shape) as a failure of that entry.

What each failure does (the "failure type" branch of the flow):

    429 rate limit        cooldown (Retry-After, else 60s); daily quota -> >=1h
    401/403 bad key       provider disabled with backoff 10min -> 1h -> 6h, logged
    402 out of credits    provider disabled with backoff 1h -> 4h -> 24h (Hugging Face)
    400/422 bad request   NOT retried; entry skipped for this request; if an entry
                          keeps rejecting requests it is parked for 10 minutes
    413 / too large       skipped for this request only, no penalty
    404 model not found   entry parked 15 minutes
    timeout / 5xx         short escalating cooldown (5s, 15s, 45s ... max 2min)

State is in memory, which is right for the single uvicorn process the project
runs. With several workers each worker keeps its own budget, so lower the *_RPM
values (or move the counters to Redis).
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import Settings, get_settings

logger = logging.getLogger("careerprep.llm")

T = TypeVar("T")

# Above this wait it is not "busy", it is "unavailable" (disabled key, daily quota...).
_UNAVAILABLE_WAIT_SECONDS = 300.0


# --------------------------------------------------------------------------- errors


class LLMError(Exception):
    """Base class for router failures."""


class LLMBusyError(LLMError):
    """Every usable entry is at its rate budget. Safe for the client to retry soon."""

    def __init__(self, retry_after: float):
        self.retry_after = max(1, int(retry_after + 0.999))
        super().__init__(f"All AI providers are busy. Try again in ~{self.retry_after}s.")


class LLMUnavailableError(LLMError):
    """No entry can serve this request right now (no keys, all failed, all parked)."""


# --------------------------------------------------------------------------- chain config


@dataclass(frozen=True)
class ChainEntry:
    provider: str
    model: str
    kind: str  # "gemini" (native client) | "openai_compat"
    api_key: str
    base_url: Optional[str]
    rpm: int
    tpm: int  # 0 = not enforced
    budget_key: str  # entries sharing a key share RPM/TPM windows (account-wide limits)
    merge_system: bool = False
    extra_body: Optional[dict] = None
    json_mode: bool = False

    @property
    def id(self) -> str:
        return f"{self.provider}:{self.model}"


# provider -> (kind, base_url, key attr, rpm attr, tpm attr or None, account_wide)
_PROVIDERS: dict[str, tuple[str, Optional[str], str, str, Optional[str], bool]] = {
    "groq": ("openai_compat", "https://api.groq.com/openai/v1", "groq_api_key", "groq_rpm", "groq_tpm", False),
    "openrouter": ("openai_compat", "https://openrouter.ai/api/v1", "openrouter_api_key", "openrouter_rpm", None, True),
    "gemini": ("gemini", None, "google_api_key", "gemini_rpm", None, False),
    "huggingface": ("openai_compat", "https://router.huggingface.co/v1", "huggingface_api_key", "huggingface_rpm", None, True),
    "cerebras": ("openai_compat", "https://api.cerebras.ai/v1", "cerebras_api_key", "cerebras_rpm", None, False),
    "mistral": ("openai_compat", "https://api.mistral.ai/v1", "mistral_api_key", "mistral_rpm", None, False),
    "openai": ("openai_compat", None, "openai_api_key", "openai_rpm", None, False),
}
# Providers where a quota/credit problem applies to every model on the account.
_ACCOUNT_WIDE = {name for name, row in _PROVIDERS.items() if row[5]}


def parse_chain(settings: Settings) -> tuple[list[ChainEntry], list[str]]:
    """Return (usable entries in order, human-readable list of skipped entries)."""
    entries: list[ChainEntry] = []
    skipped: list[str] = []
    seen: set[str] = set()
    merge_tokens = [t.strip().lower() for t in settings.llm_merge_system_for.split(",") if t.strip()]
    effort = settings.llm_reasoning_effort.strip().lower()

    for raw in re.split(r"[,\n]", settings.llm_chain):
        raw = raw.strip()
        if not raw:
            continue
        provider, sep, model = raw.partition(":")  # model may contain ':' (e.g. ":free")
        provider, model = provider.strip().lower(), model.strip()
        if not sep or not model:
            logger.warning("LLM_CHAIN entry %r is not 'provider:model' - ignored", raw)
            continue
        row = _PROVIDERS.get(provider)
        if row is None:
            logger.warning("LLM_CHAIN entry %r: unknown provider %r - ignored", raw, provider)
            continue
        kind, base_url, key_attr, rpm_attr, tpm_attr, account_wide = row
        entry_id = f"{provider}:{model}"
        if entry_id in seen:
            continue
        seen.add(entry_id)

        api_key = (getattr(settings, key_attr, "") or "").strip()
        if not api_key:
            skipped.append(f"{entry_id} (no API key)")
            continue

        lower = model.lower()
        entries.append(
            ChainEntry(
                provider=provider,
                model=model,
                kind=kind,
                api_key=api_key,
                base_url=base_url,
                rpm=max(1, int(getattr(settings, rpm_attr))),
                tpm=max(0, int(getattr(settings, tpm_attr))) if tpm_attr else 0,
                budget_key=provider if account_wide else entry_id,
                merge_system=any(t in lower for t in merge_tokens),
                extra_body=(
                    {"reasoning_effort": effort}
                    if effort and "gpt-oss" in lower and provider in ("groq", "huggingface")
                    else None
                ),
                json_mode=bool(provider == "groq" and settings.groq_json_mode),
            )
        )
    return entries, skipped


def default_model_factory(entry: ChainEntry, temperature: float):
    """Build a LangChain chat model with LangChain's own retries switched off.

    The router owns retry/failover. LangChain's Gemini client retries 6 times by
    default, which turns one request into up to 7 hits on a 5-requests-per-minute key.
    """
    if entry.kind == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Google recommends leaving temperature at 1.0 for Gemini 3.x models.
        temp = 1.0 if entry.model.startswith("gemini-3") else temperature
        kwargs: dict[str, Any] = dict(model=entry.model, google_api_key=entry.api_key, temperature=temp)
        try:
            return ChatGoogleGenerativeAI(max_retries=0, **kwargs)
        except TypeError:
            return ChatGoogleGenerativeAI(**kwargs)

    from langchain_openai import ChatOpenAI

    kwargs = dict(model=entry.model, api_key=entry.api_key, temperature=temperature, max_retries=0)
    if entry.base_url:
        kwargs["base_url"] = entry.base_url
    if entry.extra_body:
        kwargs["extra_body"] = dict(entry.extra_body)
    if entry.json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return ChatOpenAI(**kwargs)


# --------------------------------------------------------------------------- budgets


class _Budget:
    """Sliding 60s window of requests AND tokens. reserve() is synchronous, so the
    check-then-record step can't be interleaved by another coroutine."""

    def __init__(self, rpm: int, tpm: int, window: float = 60.0):
        self.rpm, self.tpm, self.window = rpm, tpm, window
        self._req: deque[float] = deque()
        self._tok: deque[list] = deque()  # [timestamp, tokens]

    def _prune(self, now: float) -> None:
        while self._req and now - self._req[0] >= self.window:
            self._req.popleft()
        while self._tok and now - self._tok[0][0] >= self.window:
            self._tok.popleft()

    def wait_time(self, now: float, need: int) -> float:
        self._prune(now)
        wait = 0.0
        if len(self._req) >= self.rpm:
            wait = self._req[0] + self.window - now
        if self.tpm:
            running = sum(t for _, t in self._tok)
            if running + need > self.tpm:
                for ts, tokens in self._tok:
                    running -= tokens
                    if running + need <= self.tpm:
                        wait = max(wait, ts + self.window - now)
                        break
                else:
                    wait = math.inf  # can never fit (callers pre-filter this)
        return max(0.0, wait)

    def reserve(self, now: float, need: int) -> Optional[list]:
        if self.wait_time(now, need) > 0:
            return None
        self._req.append(now)
        rec = [now, need]
        self._tok.append(rec)
        return rec

    def adjust(self, rec: list, actual_tokens: int) -> None:
        rec[1] = actual_tokens

    def used(self, now: float) -> tuple[int, int]:
        self._prune(now)
        return len(self._req), sum(t for _, t in self._tok)


@dataclass
class _ProviderHealth:
    disabled_until: float = 0.0
    consecutive_failures: int = 0
    reason: str = ""


@dataclass
class _EntryState:
    entry: ChainEntry
    budget: _Budget
    health: _ProviderHealth
    cooldown_until: float = 0.0
    parked_until: float = 0.0
    consecutive_rate_limits: int = 0
    consecutive_transient: int = 0
    consecutive_bad_requests: int = 0
    total_calls: int = 0
    total_success: int = 0
    total_failures: int = 0
    last_error: str = ""
    models: dict[float, Any] = field(default_factory=dict)

    def blocked_for(self, now: float, need: int) -> float:
        """Seconds until this entry can serve a request of `need` tokens (0 = now)."""
        return max(
            self.budget.wait_time(now, need),
            self.cooldown_until - now,
            self.parked_until - now,
            self.health.disabled_until - now,
            0.0,
        )

    def too_large(self, need: int) -> bool:
        return bool(self.entry.tpm) and need > self.entry.tpm


# --------------------------------------------------------------------------- error classification

_DAILY_RE = re.compile(r"per[\s_-]?day|daily|requests per day|\brpd\b|tokens per day|\btpd\b", re.I)
_KEY_RE = re.compile(
    r"(AIza[0-9A-Za-z_\-]{10,}|gsk_[0-9A-Za-z]{10,}|sk-[0-9A-Za-z_\-]{10,}|hf_[0-9A-Za-z]{10,}|Bearer\s+\S+)"
)


def _status_code(exc: BaseException) -> Optional[int]:
    for obj, attr in ((exc, "status_code"), (getattr(exc, "response", None), "status_code"), (exc, "code")):
        val = getattr(obj, attr, None) if obj is not None else None
        if isinstance(val, int) and 100 <= val <= 599:
            return val
    return None


def classify_error(exc: BaseException) -> str:
    """rate_limit | credits | auth | bad_model | too_large | bad_request | timeout | transient"""
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    status = _status_code(exc)
    text = f"{type(exc).__name__} {exc}".lower()

    # Message checks first: Gemini reports a bad key as HTTP 400.
    if any(p in text for p in ("api key not valid", "api_key_invalid", "invalid api key", "incorrect api key", "unauthenticated")):
        return "auth"
    if status == 429 or any(p in text for p in ("resource_exhausted", "resource has been exhausted", "rate limit", "rate_limit")):
        return "rate_limit"
    if status == 402 or "payment required" in text or "insufficient credits" in text:
        return "credits"
    if status in (401, 403):
        return "auth"
    if status == 413 or "request too large" in text or "context length" in text or "maximum context" in text:
        return "too_large"
    if status == 404 or ("model" in text and ("not found" in text or "does not exist" in text)):
        return "bad_model"
    if status in (400, 422):
        return "bad_request"
    if "quota" in text:
        return "rate_limit"
    return "transient"


def _retry_after_seconds(exc: BaseException) -> Optional[float]:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers:
        try:
            val = headers.get("retry-after")
            if val:
                return float(val)
        except (TypeError, ValueError):
            pass
    m = re.search(r"retry[^0-9]{0,30}([0-9]+(?:\.[0-9]+)?)\s*s", str(exc), re.I)
    return float(m.group(1)) if m else None


def _safe_message(exc: BaseException) -> str:
    """Short, key-free description for logs and the admin status view."""
    return f"{type(exc).__name__}: {_KEY_RE.sub('***', str(exc))[:160]}"


def content_to_text(content: Any) -> str:
    """LangChain message content can be a str or a list of parts (Gemini/Gemma)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type", "text") == "text":
                parts.append(str(part.get("text", "")))
        return "".join(parts)
    return str(content)


def estimate_tokens(*texts: str) -> int:
    """Cheap conservative estimate (~3.5 characters per token)."""
    return math.ceil(sum(len(t) for t in texts) / 3.5)


# --------------------------------------------------------------------------- router


class LLMRouter:
    def __init__(
        self,
        entries: list[ChainEntry],
        *,
        skipped: Optional[list[str]] = None,
        model_factory: Callable[[ChainEntry, float], Any] = default_model_factory,
        request_timeout: float = 60.0,
        max_wait: float = 25.0,
        max_attempts: int = 4,
    ):
        budgets: dict[str, _Budget] = {}
        health: dict[str, _ProviderHealth] = {}
        self._states: list[_EntryState] = []
        for e in entries:
            budget = budgets.setdefault(e.budget_key, _Budget(e.rpm, e.tpm))
            self._states.append(
                _EntryState(entry=e, budget=budget, health=health.setdefault(e.provider, _ProviderHealth()))
            )
        self._skipped = skipped or []
        self._factory = model_factory
        self._timeout = request_timeout
        self._max_wait = max_wait
        self._max_attempts = max_attempts

    # -- introspection -----------------------------------------------------

    @property
    def chain(self) -> list[str]:
        return [s.entry.id for s in self._states]

    @property
    def skipped(self) -> list[str]:
        return list(self._skipped)

    def status(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        rows = []
        for s in self._states:
            reqs, toks = s.budget.used(now)
            rows.append(
                {
                    "entry": s.entry.id,
                    "requests_last_60s": f"{reqs}/{s.entry.rpm}",
                    "tokens_last_60s": f"{toks}/{s.entry.tpm}" if s.entry.tpm else toks,
                    "shared_account_budget": s.entry.budget_key == s.entry.provider,
                    "cooling_down_for_s": round(max(0.0, s.cooldown_until - now), 1),
                    "parked_for_s": round(max(0.0, s.parked_until - now), 1),
                    "provider_disabled_for_s": round(max(0.0, s.health.disabled_until - now), 1),
                    "provider_disabled_reason": s.health.reason or None,
                    "calls": s.total_calls,
                    "successes": s.total_success,
                    "failures": s.total_failures,
                    "last_error": s.last_error or None,
                }
            )
        return rows

    # -- main entry --------------------------------------------------------

    async def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float,
        parse: Callable[[str], T],
        est_output_tokens: int = 1500,
    ) -> tuple[T, str]:
        """Run one logical request. Returns (parsed_result, entry_id).

        `parse` gets the raw model text; if it raises, that entry's output is
        treated as unusable and the next entry is tried.
        """
        if not self._states:
            raise LLMUnavailableError(
                "No LLM provider is configured. Set at least one API key "
                "(GROQ_API_KEY, OPENROUTER_API_KEY, GOOGLE_API_KEY, HF_TOKEN)."
            )

        need = estimate_tokens(system, user) + max(0, est_output_tokens)
        deadline = time.monotonic() + self._max_wait
        attempts = 0
        skip: set[str] = set()  # entries not to use again for THIS request
        failures: list[str] = []

        while True:
            for st in self._states:
                eid = st.entry.id
                if eid in skip or st.too_large(need):
                    continue
                now = time.monotonic()
                if st.blocked_for(now, need) > 0:
                    continue
                rec = st.budget.reserve(now, need)
                if rec is None:
                    continue

                attempts += 1
                st.total_calls += 1
                try:
                    text, used = await self._invoke(st, system, user, temperature)
                except Exception as exc:  # noqa: BLE001 - classified below
                    kind = classify_error(exc)
                    self._record_failure(st, exc, kind)
                    failures.append(f"{eid}: {kind}")
                    if kind in ("bad_request", "too_large"):
                        skip.add(eid)  # same request would fail the same way: don't retry
                else:
                    if used:
                        st.budget.adjust(rec, used)
                    try:
                        result = parse(text)
                    except Exception as exc:  # noqa: BLE001
                        st.total_failures += 1
                        st.last_error = f"unusable output: {_safe_message(exc)}"
                        skip.add(eid)
                        failures.append(f"{eid}: bad output")
                        logger.info("%s returned unusable output: %s", eid, exc)
                    else:
                        self._record_success(st)
                        return result, eid

                if attempts >= self._max_attempts:
                    raise LLMUnavailableError(
                        f"AI providers could not complete this request after {attempts} attempts ("
                        + ", ".join(failures)
                        + ")."
                    )

            # Nothing succeeded in this pass: can waiting help?
            now = time.monotonic()
            candidates = [s for s in self._states if s.entry.id not in skip and not s.too_large(need)]
            if not candidates:
                raise LLMUnavailableError(
                    "No AI provider could handle this request (" + (", ".join(failures) or "none eligible") + ")."
                )
            wait = min(s.blocked_for(now, need) for s in candidates)
            if wait > _UNAVAILABLE_WAIT_SECONDS:
                raise LLMUnavailableError("All AI providers are temporarily unavailable.")
            if now + wait > deadline:
                raise LLMBusyError(retry_after=wait)
            await asyncio.sleep(wait + 0.05)

    # -- internals ---------------------------------------------------------

    def _model_for(self, st: _EntryState, temperature: float):
        key = round(temperature, 2)
        model = st.models.get(key)
        if model is None:
            model = self._factory(st.entry, key)
            st.models[key] = model
        return model

    async def _invoke(
        self, st: _EntryState, system: str, user: str, temperature: float
    ) -> tuple[str, Optional[int]]:
        model = self._model_for(st, temperature)
        if st.entry.merge_system:
            messages = [HumanMessage(content=f"{system}\n\n---\n\n{user}")]
        else:
            messages = [SystemMessage(content=system), HumanMessage(content=user)]
        response = await asyncio.wait_for(model.ainvoke(messages), timeout=self._timeout)
        usage = getattr(response, "usage_metadata", None)
        total = usage.get("total_tokens") if isinstance(usage, dict) else None
        return content_to_text(response.content), (int(total) if total else None)

    def _record_success(self, st: _EntryState) -> None:
        st.total_success += 1
        st.consecutive_rate_limits = 0
        st.consecutive_transient = 0
        st.consecutive_bad_requests = 0
        st.health.consecutive_failures = 0
        st.health.reason = ""

    def _record_failure(self, st: _EntryState, exc: BaseException, kind: str) -> None:
        now = time.monotonic()
        st.total_failures += 1
        st.last_error = _safe_message(exc)
        eid = st.entry.id

        if kind == "rate_limit":
            st.consecutive_rate_limits += 1
            retry = _retry_after_seconds(exc)
            if _DAILY_RE.search(str(exc)):
                # Daily quota: probing every minute is pointless. Re-check hourly (up to 6h).
                cooldown = max(retry or 0.0, 3600.0 * min(st.consecutive_rate_limits, 6))
                targets = (
                    [s for s in self._states if s.entry.provider == st.entry.provider]
                    if st.entry.provider in _ACCOUNT_WIDE
                    else [st]
                )
            else:
                cooldown = retry or 60.0
                if st.consecutive_rate_limits >= 3:
                    cooldown = max(cooldown, 600.0)  # probably a quota we can't see
                targets = [st]
            for s in targets:
                s.cooldown_until = max(s.cooldown_until, now + cooldown)
            logger.warning("%s rate-limited, cooling down %.0fs", eid, cooldown)

        elif kind in ("auth", "credits"):
            h = st.health
            h.consecutive_failures += 1
            n = h.consecutive_failures
            seconds = min(600 * 6 ** (n - 1), 21600) if kind == "auth" else min(3600 * 4 ** (n - 1), 86400)
            h.disabled_until = now + seconds
            h.reason = "API key rejected" if kind == "auth" else "out of credits"
            logger.error(
                "%s: provider %s disabled for %ds (%s). Check the key / credits in .env.",
                eid, st.entry.provider, seconds, h.reason,
            )

        elif kind == "bad_model":
            st.parked_until = now + 900.0
            logger.error("%s: model not found/available - parked 15 min. Check LLM_CHAIN.", eid)

        elif kind == "bad_request":
            st.consecutive_bad_requests += 1
            if st.consecutive_bad_requests >= 3:
                st.parked_until = now + 600.0
                st.consecutive_bad_requests = 0
                logger.error("%s rejected 3 requests in a row (%s) - parked 10 min.", eid, st.last_error)

        elif kind == "too_large":
            pass  # request-specific, no penalty

        else:  # timeout / transient: short escalating cooldown
            st.consecutive_transient += 1
            st.cooldown_until = now + min(5 * 3 ** (st.consecutive_transient - 1), 120)

        logger.info("%s failed (%s): %s", eid, kind, st.last_error)


# --------------------------------------------------------------------------- singleton

_router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        s = get_settings()
        entries, skipped = parse_chain(s)
        _router = LLMRouter(
            entries,
            skipped=skipped,
            request_timeout=s.llm_request_timeout_seconds,
            max_wait=s.llm_max_wait_seconds,
            max_attempts=s.llm_max_attempts,
        )
        if _router.chain:
            logger.info("LLM chain (in order): %s", " -> ".join(_router.chain))
        else:
            logger.error("LLM chain is EMPTY - add API keys to .env. Skipped: %s", skipped)
        if skipped:
            logger.info("LLM chain entries skipped: %s", "; ".join(skipped))
    return _router


def reset_router() -> None:
    """For tests."""
    global _router
    _router = None
