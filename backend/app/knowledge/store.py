"""FTS5 index over knowledge chunks (same SQLite file as the catalog)."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from app.catalog.store import fts_query
from app.knowledge.loader import Chunk
from app.models import CamelModel
from app.sqlite import connect, enable_wal

_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    doc, heading, body,
    tokenize = 'unicode61'
);
"""


class KnowledgeHit(CamelModel):
    doc: str
    heading: str
    body: str
    score: float


class KnowledgeStore:
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

    def replace_all_sync(self, chunks: list[Chunk]) -> int:
        with self._connect() as conn:
            conn.execute("DELETE FROM knowledge_fts")
            conn.executemany(
                "INSERT INTO knowledge_fts (doc, heading, body) VALUES (?, ?, ?)",
                [(c.doc, c.heading, c.body) for c in chunks],
            )
        return len(chunks)

    def search_sync(self, query: str, *, limit: int = 5) -> list[KnowledgeHit]:
        hits = self._search(fts_query(query), limit)
        if not hits and len(query.split()) > 1:
            hits = self._search(fts_query(query, operator="OR"), limit)
        return hits

    def _search(self, match: str | None, limit: int) -> list[KnowledgeHit]:
        if match is None:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT doc, heading, body, -bm25(knowledge_fts, 3.0, 4.0, 1.0) AS score "
                "FROM knowledge_fts WHERE knowledge_fts MATCH ? ORDER BY score DESC LIMIT ?",
                (match, limit),
            ).fetchall()
        return [
            KnowledgeHit(
                doc=r["doc"], heading=r["heading"], body=r["body"], score=round(r["score"], 3)
            )
            for r in rows
        ]

    def count_sync(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM knowledge_fts").fetchone()[0])

    async def replace_all(self, chunks: list[Chunk]) -> int:
        return await asyncio.to_thread(self.replace_all_sync, chunks)

    async def search(self, query: str, *, limit: int = 5) -> list[KnowledgeHit]:
        return await asyncio.to_thread(self.search_sync, query, limit=limit)
