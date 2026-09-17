"""Database-backed knowledge documents: edited in the UI or written by the assistant."""

from __future__ import annotations

import asyncio
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.knowledge.loader import StoredDoc

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_docs (
    name TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'ui',
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


def slugify_name(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:64].strip("-")
    return slug or "note"


def valid_name(name: str) -> bool:
    return bool(_NAME.match(name))


class KnowledgeDocStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        conn.row_factory = sqlite3.Row
        return conn

    def list_sync(self) -> list[StoredDoc]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM knowledge_docs ORDER BY name").fetchall()
        return [StoredDoc(r["name"], r["body"], r["source"], r["updated_at"]) for r in rows]

    def get_sync(self, name: str) -> StoredDoc | None:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM knowledge_docs WHERE name = ?", (name,)).fetchone()
        return StoredDoc(r["name"], r["body"], r["source"], r["updated_at"]) if r else None

    def put_sync(self, name: str, body: str, source: str = "ui") -> StoredDoc:
        now = datetime.now(tz=UTC).timestamp()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO knowledge_docs (name, body, source, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET body = excluded.body, source = excluded.source, "
                "updated_at = excluded.updated_at",
                (name, body, source, now),
            )
        return StoredDoc(name, body, source, now)

    def delete_sync(self, name: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM knowledge_docs WHERE name = ?", (name,))
        return cur.rowcount > 0

    def prompt_sync(self) -> str | None:
        with self._connect() as conn:
            r = conn.execute("SELECT value FROM knowledge_settings WHERE key = 'prompt'").fetchone()
        return r["value"] if r else None

    def set_prompt_sync(self, text: str | None) -> None:
        with self._connect() as conn:
            if text is None or not text.strip():
                conn.execute("DELETE FROM knowledge_settings WHERE key = 'prompt'")
            else:
                conn.execute(
                    "INSERT INTO knowledge_settings (key, value) VALUES ('prompt', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (text,),
                )

    def signature_sync(self) -> tuple[tuple[str, float], ...]:
        with self._connect() as conn:
            rows = conn.execute("SELECT name, updated_at FROM knowledge_docs").fetchall()
            prompt = conn.execute(
                "SELECT value FROM knowledge_settings WHERE key = 'prompt'"
            ).fetchone()
        entries = [(f"db:{r['name']}", float(r["updated_at"])) for r in rows]
        if prompt:
            entries.append(("db:prompt", float(len(prompt["value"])) if prompt else 0.0))
        return tuple(sorted(entries))

    async def list(self) -> list[StoredDoc]:
        return await asyncio.to_thread(self.list_sync)

    async def get(self, name: str) -> StoredDoc | None:
        return await asyncio.to_thread(self.get_sync, name)

    async def put(self, name: str, body: str, source: str = "ui") -> StoredDoc:
        return await asyncio.to_thread(self.put_sync, name, body, source)

    async def delete(self, name: str) -> bool:
        return await asyncio.to_thread(self.delete_sync, name)

    async def prompt(self) -> str | None:
        return await asyncio.to_thread(self.prompt_sync)

    async def set_prompt(self, text: str | None) -> None:
        await asyncio.to_thread(self.set_prompt_sync, text)
