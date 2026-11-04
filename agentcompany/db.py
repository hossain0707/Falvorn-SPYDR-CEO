"""SQLite persistence, transactions, and tamper-evident audit chain."""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=12, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=12000")
    con.execute("PRAGMA journal_mode=WAL")
    return con


@contextmanager
def transaction(path: Path):
    con = connect(path)
    try:
        con.execute("BEGIN IMMEDIATE")
        yield con
        con.execute("COMMIT")
    except Exception:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    finally:
        con.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 csrf TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS companies (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, monthly_budget_usd REAL NOT NULL
 CHECK(monthly_budget_usd>0), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agents (
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 name TEXT NOT NULL, role TEXT NOT NULL, instructions TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS goals (
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 title TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
 company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 agent_id TEXT REFERENCES agents(id) ON DELETE SET NULL,
 title TEXT NOT NULL, description TEXT NOT NULL, risk TEXT NOT NULL,
 status TEXT NOT NULL, estimated_cost_usd REAL NOT NULL DEFAULT 0,
 output TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
 id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
 goal_id TEXT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
 type TEXT NOT NULL, summary TEXT NOT NULL, payload TEXT NOT NULL,
 status TEXT NOT NULL, decided_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
 agent_id TEXT REFERENCES agents(id) ON DELETE SET NULL, model TEXT NOT NULL,
 input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
 cost_usd REAL NOT NULL, status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
 event TEXT NOT NULL, entity_id TEXT NOT NULL, details TEXT NOT NULL,
 previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_company ON tasks(company_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_time ON runs(created_at DESC);
"""


def init(path: Path) -> None:
    con = connect(path)
    try:
        con.executescript(SCHEMA)
    finally:
        con.close()


def audit(con: sqlite3.Connection, actor: str, event: str, entity_id: str, details: dict | None = None):
    row = con.execute("SELECT entry_hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
    prev = row["entry_hash"] if row else "0" * 64
    at = now()
    payload = json.dumps(details or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    message = json.dumps([prev, at, actor, event, entity_id, payload], separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
    con.execute(
        "INSERT INTO audit(at,actor,event,entity_id,details,previous_hash,entry_hash) VALUES(?,?,?,?,?,?,?)",
        (at, actor, event, entity_id, payload, prev, digest),
    )


def verify_chain(path: Path) -> tuple[bool, int]:
    con = connect(path)
    try:
        prior = "0" * 64
        count = 0
        for row in con.execute("SELECT * FROM audit ORDER BY id"):
            if row["previous_hash"] != prior:
                return False, count
            message = json.dumps([prior, row["at"], row["actor"], row["event"], row["entity_id"], row["details"]], separators=(",", ":"), ensure_ascii=False)
            digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
            if digest != row["entry_hash"]:
                return False, count
            prior, count = digest, count + 1
        return True, count
    finally:
        con.close()


def rows(con, sql: str, args: tuple = ()) -> list[dict]:
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def row(con, sql: str, args: tuple = ()) -> dict | None:
    r = con.execute(sql, args).fetchone()
    return dict(r) if r else None
