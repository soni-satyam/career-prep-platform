"""PART 7a - SQLite persistence (stdlib only, free, zero setup).

Tables:  sessions (inputs + final report)  |  events (progress log for SSE)  |  attempts (practice history)
A fresh connection per call keeps this thread-safe with FastAPI's thread pool.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    company_name TEXT NOT NULL,
    job_description TEXT NOT NULL,
    resume_text TEXT NOT NULL,
    report TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    node TEXT,
    message TEXT NOT NULL DEFAULT '',
    data TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    feedback TEXT NOT NULL,
    follow_up TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

TERMINAL_STATUSES = {"completed", "failed", "rejected"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _conn():
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)


# ---------------- sessions ----------------
def create_session(session_id: str, company_name: str, job_description: str, resume_text: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO sessions (id,status,company_name,job_description,resume_text,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (session_id, "pending", company_name, job_description, resume_text, _now()),
        )


def update_session(session_id: str, *, status: str | None = None,
                   report: dict | None = None, error: str | None = None) -> None:
    sets, vals = [], []
    if status is not None:
        sets.append("status=?"); vals.append(status)
    if report is not None:
        sets.append("report=?"); vals.append(json.dumps(report))
    if error is not None:
        sets.append("error=?"); vals.append(error)
    if not sets:
        return
    with _conn() as c:
        c.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id=?", (*vals, session_id))


def get_session(session_id: str, private: bool = False) -> dict | None:
    """private=True also returns resume_text / job_description (used server-side only)."""
    with _conn() as c:
        row = c.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["report"] = json.loads(d["report"]) if d["report"] else None
    if not private:
        d.pop("resume_text"); d.pop("job_description")
    return d


def get_status(session_id: str) -> str | None:
    with _conn() as c:
        row = c.execute("SELECT status FROM sessions WHERE id=?", (session_id,)).fetchone()
    return row["status"] if row else None


def delete_session(session_id: str) -> bool:
    with _conn() as c:
        return c.execute("DELETE FROM sessions WHERE id=?", (session_id,)).rowcount > 0


def purge_old(days: int) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _conn() as c:
        return c.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,)).rowcount


def mark_interrupted() -> int:
    """After a restart, runs that were in flight can never finish."""
    with _conn() as c:
        rows = c.execute("SELECT id FROM sessions WHERE status IN ('pending','running')").fetchall()
    for r in rows:
        add_event(r["id"], "failed", message="Server restarted while this run was in progress.")
        update_session(r["id"], status="failed", error="Server restarted while this run was in progress.")
    return len(rows)


# ---------------- events ----------------
def add_event(session_id: str, type: str, node: str | None = None,
              message: str = "", data: dict | None = None) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO events (session_id,type,node,message,data,created_at) VALUES (?,?,?,?,?,?)",
            (session_id, type, node, message, json.dumps(data) if data else None, _now()),
        )


def get_events_after(session_id: str, after_id: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM events WHERE session_id=? AND id>? ORDER BY id", (session_id, after_id)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["data"] = json.loads(d["data"]) if d["data"] else None
        out.append(d)
    return out


# ---------------- practice attempts ----------------
def add_attempt(session_id: str, question_id: str, question: str, answer: str,
                feedback: dict, follow_up: dict) -> tuple[int, str]:
    created = _now()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO attempts (session_id,question_id,question,answer,feedback,follow_up,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (session_id, question_id, question, answer, json.dumps(feedback), json.dumps(follow_up), created),
        )
        return cur.lastrowid, created


def get_attempts(session_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM attempts WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["attempt_id"] = d.pop("id")
        d["feedback"] = json.loads(d["feedback"])
        d["follow_up"] = json.loads(d["follow_up"])
        out.append(d)
    return out
