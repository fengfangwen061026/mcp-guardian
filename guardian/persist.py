from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .knowledge import ALL_ENTRIES

DEFAULT_DB_PATH = Path.home() / ".claude" / "guardian" / "events.db"
PERSIST_DIR = os.path.expanduser("~/.claude/guardian/sessions")
_SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,'\"]+")


class OffsetStore:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    error_class TEXT,
                    error_type TEXT,
                    params_sig TEXT,
                    error_msg TEXT,
                    created_at REAL NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS error_patterns (
                    pattern_key TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL,
                    error_type TEXT,
                    count INTEGER DEFAULT 0,
                    last_seen REAL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_base (
                    id TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    base_priority INTEGER NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS priority_offsets (
                    knowledge_id TEXT PRIMARY KEY,
                    offset REAL DEFAULT 0.0,
                    hit_count INTEGER DEFAULT 0,
                    miss_count INTEGER DEFAULT 0,
                    last_updated REAL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    risk REAL NOT NULL,
                    reasons_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
            """)
            c.executemany(
                "INSERT OR REPLACE INTO knowledge_base (id, tool_name, category, title, content, base_priority) VALUES (?, ?, ?, ?, ?, ?)",
                [(e.id, e.tool_name, e.category, e.title, e.content, e.base_priority) for e in ALL_ENTRIES],
            )

    def get_offset(self, knowledge_id: str) -> float:
        with self._conn() as c:
            row = c.execute("SELECT offset FROM priority_offsets WHERE knowledge_id = ?", (knowledge_id,)).fetchone()
            return row[0] if row else 0.0

    async def create_approval(self, session_id: str, tool_name: str, params_json: str, risk: float, reasons_json: str, ttl_seconds: int = 900) -> dict:
        async with self._lock:
            return await asyncio.get_event_loop().run_in_executor(None, self._sync_create_approval, session_id, tool_name, params_json, risk, reasons_json, ttl_seconds)

    def _sync_create_approval(self, session_id: str, tool_name: str, params_json: str, risk: float, reasons_json: str, ttl_seconds: int) -> dict:
        now = time.time()
        approval_id = uuid.uuid4().hex
        expires_at = now + ttl_seconds
        with self._conn() as c:
            c.execute(
                "INSERT INTO approvals (approval_id, session_id, tool_name, params_json, risk, reasons_json, status, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (approval_id, session_id, tool_name, params_json, risk, reasons_json, "pending", now, expires_at),
            )
        return {"approval_id": approval_id, "expires_at": expires_at}

    async def list_pending_approvals(self, session_id: str | None = None) -> list[dict]:
        async with self._lock:
            return await asyncio.get_event_loop().run_in_executor(None, self._sync_list_pending_approvals, session_id)

    def _sync_list_pending_approvals(self, session_id: str | None = None) -> list[dict]:
        now = time.time()
        with self._conn() as c:
            c.execute("UPDATE approvals SET status = 'expired' WHERE status = 'pending' AND expires_at <= ?", (now,))
            query = "SELECT approval_id, session_id, tool_name, params_json, risk, reasons_json, status, created_at, expires_at FROM approvals WHERE status = 'pending'"
            args: tuple = ()
            if session_id:
                query += " AND session_id = ?"
                args = (session_id,)
            query += " ORDER BY created_at ASC"
            rows = c.execute(query, args).fetchall()
        return [
            {
                "approval_id": row[0],
                "session_id": row[1],
                "tool_name": row[2],
                "params": json.loads(row[3]),
                "risk": row[4],
                "reasons": json.loads(row[5]),
                "status": row[6],
                "created_at": row[7],
                "expires_at": row[8],
            }
            for row in rows
        ]

    async def record_event(self, session_id: str, tool_name: str, success: bool, params_sig: str, response: dict) -> None:
        async with self._lock:
            await asyncio.get_event_loop().run_in_executor(None, self._sync_record_event, session_id, tool_name, success, params_sig, response)

    def _sync_record_event(self, session_id: str, tool_name: str, success: bool, params_sig: str, response: dict) -> None:
        now = time.time()
        error_type = response.get("error_type", "")
        error_msg = _SECRET_RE.sub(r"\1=[REDACTED]", str(response.get("error", "")))[:500]
        with self._conn() as c:
            c.execute(
                "INSERT INTO events (session_id, tool_name, success, error_class, error_type, params_sig, error_msg, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, tool_name, 1 if success else 0, response.get("error_class", ""), error_type, params_sig, error_msg, now),
            )
            if error_type:
                key = f"{tool_name}:{error_type}"
                c.execute("INSERT INTO error_patterns (pattern_key, tool_name, error_type, count, last_seen) VALUES (?, ?, ?, 1, ?) ON CONFLICT(pattern_key) DO UPDATE SET count = count + 1, last_seen = excluded.last_seen", (key, tool_name, error_type, now))

    async def adjust_on_error(self, knowledge_ids: list[str]) -> None:
        async with self._lock:
            await asyncio.get_event_loop().run_in_executor(None, self._sync_adjust, knowledge_ids, -0.3, "hit")

    async def adjust_on_success(self, knowledge_ids: list[str]) -> None:
        async with self._lock:
            await asyncio.get_event_loop().run_in_executor(None, self._sync_adjust, knowledge_ids, 0.05, None)

    async def adjust_on_guidance_miss(self, knowledge_ids: list[str]) -> None:
        async with self._lock:
            await asyncio.get_event_loop().run_in_executor(None, self._sync_adjust_miss, knowledge_ids)

    def _sync_adjust(self, ids: list[str], delta: float, marker: str | None) -> None:
        now = time.time()
        with self._conn() as c:
            for kid in ids:
                row = c.execute("SELECT offset, hit_count, miss_count FROM priority_offsets WHERE knowledge_id = ?", (kid,)).fetchone()
                if row is None:
                    c.execute("INSERT INTO priority_offsets (knowledge_id, offset, hit_count, miss_count, last_updated) VALUES (?, ?, ?, 0, ?)", (kid, max(-5.0, min(3.0, delta)), 1 if marker == "hit" else 0, now))
                else:
                    new_offset = max(-5.0, min(3.0, row[0] + delta))
                    new_hit = row[1] + (1 if marker == "hit" else 0)
                    c.execute("UPDATE priority_offsets SET offset = ?, hit_count = ?, last_updated = ? WHERE knowledge_id = ?", (new_offset, new_hit, now, kid))

    def _sync_adjust_miss(self, ids: list[str]) -> None:
        now = time.time()
        with self._conn() as c:
            for kid in ids:
                row = c.execute("SELECT offset, hit_count, miss_count FROM priority_offsets WHERE knowledge_id = ?", (kid,)).fetchone()
                if row is None:
                    continue
                offset, hit, miss = row
                new_miss = miss + 1
                if new_miss > 3 and new_miss > hit:
                    c.execute("UPDATE priority_offsets SET offset = ?, miss_count = ?, last_updated = ? WHERE knowledge_id = ?", (min(3.0, offset + 1.0), new_miss, now, kid))
                else:
                    c.execute("UPDATE priority_offsets SET miss_count = ?, last_updated = ? WHERE knowledge_id = ?", (new_miss, now, kid))

    async def daily_decay(self) -> None:
        async with self._lock:
            await asyncio.get_event_loop().run_in_executor(None, self._sync_decay)

    def _sync_decay(self) -> None:
        with self._conn() as c:
            c.execute("UPDATE priority_offsets SET offset = offset * 0.95")


async def flush_session(session) -> None:
    os.makedirs(PERSIST_DIR, exist_ok=True)
    data = getattr(session, "_priority_offsets", {})
    file_name = f"{session.session_id}_{getattr(session, 'model_hint', '_default')}.json"
    path = os.path.join(PERSIST_DIR, file_name)
    dir_name = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=dir_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


async def load_offsets(session_id: str) -> dict | None:
    path = os.path.join(PERSIST_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        prefix = f"{session_id}_"
        try:
            matches = [name for name in os.listdir(PERSIST_DIR) if name.startswith(prefix) and name.endswith(".json")]
        except FileNotFoundError:
            matches = []
        if matches:
            path = os.path.join(PERSIST_DIR, matches[0])
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
