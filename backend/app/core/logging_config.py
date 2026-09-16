"""One place that decides what reaches the console.

Goal: the console should be readable. A normal request produces one access line,
and a problem shows up as a short WARNING/ERROR line you can spot immediately.

What it does
- Root level comes from LOG_LEVEL (default INFO). Our own loggers ("careerprep*",
  "career_prep") follow it.
- SQL statements are NOT printed unless LOG_SQL=true (previously DEBUG=true made
  SQLAlchemy echo every statement, which drowned everything else).
- Chatty third-party libraries are held at WARNING (httpx, httpcore, asyncio, ...).
  Set LOG_LIBS_LEVEL=INFO or DEBUG to see them again.
- Identical consecutive log lines are collapsed ("... repeated 12 more times").
- Very long messages are truncated (LOG_MAX_MESSAGE_CHARS), e.g. LLM payloads.
- Health-check access lines are dropped.
- Tracebacks are kept for ERROR/exception records (that is what you want to read),
  but each one is a single block that starts with a one-line summary.
"""

from __future__ import annotations

import logging
import logging.config
import time
from typing import Optional

from app.core.config import Settings, get_settings

_NOISY_LIBS = (
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "asyncpg",
    "httpx",
    "httpcore",
    "urllib3",
    "asyncio",
    "watchfiles",
    "multipart",
    "passlib",
    "langsmith",
    "langchain",
    "langchain_core",
    "langgraph",
    "openai",
    "groq",
    "google",
    "grpc",
    "hpack",
    "PIL",
    "aiosqlite",
)

_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def _level(name: str, default: int) -> int:
    return _LEVELS.get((name or "").strip().upper(), default)


class TruncateFilter(logging.Filter):
    """Cut absurdly long messages (prompts, LLM responses, SQL parameter dumps)."""

    def __init__(self, max_chars: int = 600) -> None:
        super().__init__()
        self.max_chars = max_chars

    def filter(self, record: logging.LogRecord) -> bool:
        if self.max_chars <= 0:
            return True
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - never let logging break the app
            return True
        if len(msg) > self.max_chars:
            extra = len(msg) - self.max_chars
            record.msg = f"{msg[: self.max_chars]}... [+{extra} chars truncated]"
            record.args = None
        return True


class DedupFilter(logging.Filter):
    """Collapse identical consecutive messages from the same logger/level."""

    def __init__(self, window_seconds: float = 30.0) -> None:
        super().__init__()
        self.window = window_seconds
        self._last_key: Optional[tuple] = None
        self._last_time = 0.0
        self._suppressed = 0

    def filter(self, record: logging.LogRecord) -> bool:
        # Never hide tracebacks: each one is a distinct failure worth reading.
        if record.exc_info:
            self._flush_note(record)
            self._last_key = None
            return True
        try:
            key = (record.name, record.levelno, record.getMessage())
        except Exception:  # noqa: BLE001
            return True
        now = time.monotonic()
        if key == self._last_key and now - self._last_time < self.window:
            self._suppressed += 1
            self._last_time = now
            return False
        self._flush_note(record)
        self._last_key = key
        self._last_time = now
        return True

    def _flush_note(self, record: logging.LogRecord) -> None:
        if self._suppressed:
            n, self._suppressed = self._suppressed, 0
            record.msg = f"(previous message repeated {n} more times)\n{record.getMessage()}"
            record.args = None


class DropHealthAccess(logging.Filter):
    """uvicorn access lines for GET /health (probes / polling) are pure noise."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            return "/health" not in record.getMessage()
        except Exception:  # noqa: BLE001
            return True


def setup_logging(settings: Optional[Settings] = None) -> None:
    """Idempotent: safe to call more than once (uvicorn --reload re-imports the app)."""
    s = settings or get_settings()
    app_level = _level(s.log_level, logging.INFO)
    libs_level = _level(s.log_libs_level, logging.WARNING)

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "truncate": {"()": TruncateFilter, "max_chars": s.log_max_message_chars},
            "dedup": {"()": DedupFilter},
            "no_health": {"()": DropHealthAccess},
        },
        "formatters": {
            "compact": {
                "format": "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                "datefmt": "%H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "compact",
                "filters": ["truncate", "dedup"],
            },
            "access": {
                "class": "logging.StreamHandler",
                "formatter": "compact",
                "filters": ["no_health"],
            },
        },
        "root": {"level": app_level, "handlers": ["console"]},
        "loggers": {
            # uvicorn keeps its own handlers; just route/level them predictably.
            "uvicorn": {"handlers": ["console"], "level": logging.INFO, "propagate": False},
            "uvicorn.error": {"handlers": ["console"], "level": logging.INFO, "propagate": False},
            "uvicorn.access": {
                "handlers": ["access"],
                "level": logging.INFO if s.log_access else logging.WARNING,
                "propagate": False,
            },
        },
    }
    logging.config.dictConfig(config)

    for name in _NOISY_LIBS:
        logging.getLogger(name).setLevel(libs_level)

    # SQLAlchemy: engine echo is controlled here, never by DEBUG.
    sql_level = logging.INFO if s.log_sql else logging.WARNING
    logging.getLogger("sqlalchemy.engine").setLevel(sql_level)
