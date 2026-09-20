"""SQLite table of chat turns, per dashboard. Lives in the project database."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.chat.models import ChatHistory, ChatTurnRecord
from app.sqlite import connect, enable_wal

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_turns (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    dashboard_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    reasoning TEXT NOT NULL DEFAULT '',
    blocks TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_turns_dashboard ON chat_turns (dashboard_id, seq);
"""

# Older turns are dropped so a busy dashboard does not grow without bound.
MAX_TURNS_PER_DASHBOARD = 400


class ChatStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._schema_ready = False

    def _connect(self) -> sqlite3.Connection:
        conn = connect(self.path)
        if not self._schema_ready:
            enable_wal(conn)
            conn.executescript(_SCHEMA)
            self._schema_ready = True
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _record(row: sqlite3.Row) -> ChatTurnRecord:
        return ChatTurnRecord(
            id=row["id"],
            seq=row["seq"],
            role=row["role"],
            content=row["content"],
            reasoning=row["reasoning"],
            blocks=json.loads(row["blocks"]),
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def append_sync(
        self,
        dashboard_id: str,
        *,
        id: str,
        role: str,
        content: str = "",
        reasoning: str = "",
        blocks: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> ChatTurnRecord:
        now = datetime.now(tz=UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chat_turns (id, dashboard_id, role, content, reasoning, blocks, "
                "error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    id,
                    dashboard_id,
                    role,
                    content,
                    reasoning,
                    json.dumps(blocks or [], default=str),
                    error,
                    now,
                ),
            )
            conn.execute(
                "DELETE FROM chat_turns WHERE dashboard_id = ? AND seq NOT IN ("
                "SELECT seq FROM chat_turns WHERE dashboard_id = ? ORDER BY seq DESC LIMIT ?)",
                (dashboard_id, dashboard_id, MAX_TURNS_PER_DASHBOARD),
            )
            row = conn.execute("SELECT * FROM chat_turns WHERE id = ?", (id,)).fetchone()
        return self._record(row)

    def history_sync(self, dashboard_id: str, *, after: int = 0, limit: int = 100) -> ChatHistory:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM (SELECT * FROM chat_turns WHERE dashboard_id = ? AND seq > ? "
                "ORDER BY seq DESC LIMIT ?) ORDER BY seq",
                (dashboard_id, after, limit),
            ).fetchall()
            last = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM chat_turns WHERE dashboard_id = ?",
                (dashboard_id,),
            ).fetchone()[0]
        return ChatHistory(turns=[self._record(r) for r in rows], last_seq=int(last))

    def clear_sync(self, dashboard_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM chat_turns WHERE dashboard_id = ?", (dashboard_id,))

    # ---- async wrappers ---------------------------------------------------

    async def append(self, dashboard_id: str, **turn: Any) -> ChatTurnRecord:
        return await asyncio.to_thread(self.append_sync, dashboard_id, **turn)

    async def history(self, dashboard_id: str, *, after: int = 0, limit: int = 100) -> ChatHistory:
        return await asyncio.to_thread(self.history_sync, dashboard_id, after=after, limit=limit)

    async def clear(self, dashboard_id: str) -> None:
        await asyncio.to_thread(self.clear_sync, dashboard_id)
