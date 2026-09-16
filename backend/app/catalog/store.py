"""SQLite + FTS5 storage for the metric catalog."""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from app.catalog.models import CatalogStatus, MetricEntry, SearchHit

FTS_COLUMNS = ("name", "tokens", "help", "category", "labels")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metrics (
    name TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    help TEXT NOT NULL,
    unit TEXT NOT NULL,
    category TEXT NOT NULL,
    exporter TEXT,
    labels TEXT NOT NULL,          -- JSON array of label names
    labels_sampled INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS metrics_category ON metrics(category);
CREATE TABLE IF NOT EXISTS catalog_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_TOKEN = re.compile(r"[A-Za-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def name_tokens(name: str) -> str:
    """Searchable words of a metric name.

    ``node_memory_MemAvailable_bytes`` → ``node memory mem available bytes``. The FTS
    tokenizer already splits on ``_``; this adds camelCase boundaries so that
    "available" finds ``MemAvailable``.
    """
    words = []
    for part in name.split("_"):
        words.extend(w.lower() for w in _CAMEL.split(part) if w)
    return " ".join(dict.fromkeys(words))


def fts_query(text: str, *, operator: str = "AND") -> str | None:
    """Turn free text into an FTS5 prefix query: ``cpu usage`` → ``"cpu"* AND "usage"*``.

    Metric names are split on ``_`` by the tokenizer, so searching ``node_cpu``
    matches the tokens ``node`` and ``cpu``.
    """
    tokens = [t.lower() for t in _TOKEN.findall(text)]
    if not tokens:
        return None
    return f" {operator} ".join(f'"{t}"*' for t in tokens)


class CatalogStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        self._ensure_fts(conn)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _ensure_fts(conn: sqlite3.Connection) -> None:
        """Create the FTS index; if its columns changed in a newer build, drop and rebuild it."""
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'metrics_fts'"
        ).fetchone()
        wanted = f"USING fts5({', '.join(FTS_COLUMNS)}, tokenize = 'unicode61')"
        if row is not None and wanted in row[0]:
            return
        if row is not None:
            conn.execute("DROP TABLE metrics_fts")
        conn.execute(f"CREATE VIRTUAL TABLE metrics_fts {wanted}")
        # Re-index whatever is already stored so search keeps working without a rebuild.
        conn.execute(
            "INSERT INTO metrics_fts (name, tokens, help, category, labels) "
            "SELECT name, name, help, category, labels FROM metrics"
        )
        for (name,) in conn.execute("SELECT name FROM metrics").fetchall():
            conn.execute(
                "UPDATE metrics_fts SET tokens = ? WHERE name = ?", (name_tokens(name), name)
            )

    # ---- writes ---------------------------------------------------------

    def replace_all_sync(self, entries: Iterable[MetricEntry]) -> int:
        rows = [
            (
                e.name,
                e.type,
                e.help,
                e.unit,
                e.category,
                e.exporter,
                json.dumps(e.labels),
                int(e.labels_sampled),
            )
            for e in entries
        ]
        with self._connect() as conn:
            conn.execute("DELETE FROM metrics")
            conn.execute("DELETE FROM metrics_fts")
            conn.executemany(
                "INSERT INTO metrics (name, type, help, unit, category, exporter, labels, "
                "labels_sampled) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.executemany(
                "INSERT INTO metrics_fts (name, tokens, help, category, labels) "
                "VALUES (?, ?, ?, ?, ?)",
                [(r[0], name_tokens(r[0]), r[2], r[4], " ".join(json.loads(r[6]))) for r in rows],
            )
        return len(rows)

    def update_labels_sync(self, name: str, labels: list[str]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE metrics SET labels = ?, labels_sampled = 1 WHERE name = ?",
                (json.dumps(labels), name),
            )
            conn.execute(
                "UPDATE metrics_fts SET labels = ? WHERE name = ?", (" ".join(labels), name)
            )

    def set_meta_sync(self, **values: str | None) -> None:
        with self._connect() as conn:
            for key, value in values.items():
                if value is None:
                    conn.execute("DELETE FROM catalog_meta WHERE key = ?", (key,))
                else:
                    conn.execute(
                        "INSERT INTO catalog_meta (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (key, value),
                    )

    # ---- reads ----------------------------------------------------------

    def status_sync(self) -> CatalogStatus:
        with self._connect() as conn:
            meta = dict(conn.execute("SELECT key, value FROM catalog_meta").fetchall())
            count = conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
            categories = dict(
                conn.execute(
                    "SELECT category, COUNT(*) FROM metrics GROUP BY category ORDER BY 2 DESC"
                ).fetchall()
            )
        updated = meta.get("updated_at")
        duration = meta.get("duration_seconds")
        return CatalogStatus(
            state=meta.get("state", "idle"),  # type: ignore[arg-type]
            metric_count=count,
            updated_at=datetime.fromisoformat(updated) if updated else None,
            duration_seconds=float(duration) if duration else None,
            error=meta.get("error"),
            categories=categories,
        )

    def get_sync(self, name: str) -> MetricEntry | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM metrics WHERE name = ?", (name,)).fetchone()
        return self._entry(row) if row else None

    def search_sync(
        self, query: str, *, limit: int = 20, category: str | None = None
    ) -> list[SearchHit]:
        """Rank by FTS. All words must match; if nothing does, fall back to any word.

        The fallback means "cpu usage" still finds ``node_cpu_seconds_total`` even
        though no metric mentions "usage" — one less round trip for the agent.
        """
        hits = self._search(fts_query(query), limit=limit, category=category)
        if not hits and len(_TOKEN.findall(query)) > 1:
            hits = self._search(fts_query(query, operator="OR"), limit=limit, category=category)
        return hits

    def _search(self, match: str | None, *, limit: int, category: str | None) -> list[SearchHit]:
        with self._connect() as conn:
            if match is None:
                sql = "SELECT m.*, 0.0 AS score FROM metrics m"
                params: list[object] = []
                if category:
                    sql += " WHERE m.category = ?"
                    params.append(category)
                sql += " ORDER BY m.name LIMIT ?"
                params.append(limit)
                rows = conn.execute(sql, params).fetchall()
            else:
                # bm25 returns lower-is-better; weights boost name and category matches.
                sql = (
                    "SELECT m.*, -bm25(metrics_fts, 8.0, 6.0, 1.0, 3.0, 1.5) AS score "
                    "FROM metrics_fts JOIN metrics m ON m.name = metrics_fts.name "
                    "WHERE metrics_fts MATCH ?"
                )
                params = [match]
                if category:
                    sql += " AND m.category = ?"
                    params.append(category)
                sql += " ORDER BY score DESC, m.name LIMIT ?"
                params.append(limit)
                rows = conn.execute(sql, params).fetchall()
        return [SearchHit(**self._entry(r).model_dump(), score=round(r["score"], 3)) for r in rows]

    def names_sync(self, *, unsampled_only: bool = False) -> list[str]:
        with self._connect() as conn:
            sql = "SELECT name FROM metrics"
            if unsampled_only:
                sql += " WHERE labels_sampled = 0"
            return [r[0] for r in conn.execute(sql + " ORDER BY name").fetchall()]

    @staticmethod
    def _entry(row: sqlite3.Row) -> MetricEntry:
        return MetricEntry(
            name=row["name"],
            type=row["type"],
            help=row["help"],
            unit=row["unit"],
            category=row["category"],
            exporter=row["exporter"],
            labels=json.loads(row["labels"]),
            labels_sampled=bool(row["labels_sampled"]),
        )

    # ---- async facade -----------------------------------------------------

    async def replace_all(self, entries: list[MetricEntry]) -> int:
        return await asyncio.to_thread(self.replace_all_sync, entries)

    async def update_labels(self, name: str, labels: list[str]) -> None:
        await asyncio.to_thread(self.update_labels_sync, name, labels)

    async def set_meta(self, **values: str | None) -> None:
        await asyncio.to_thread(lambda: self.set_meta_sync(**values))

    async def status(self) -> CatalogStatus:
        return await asyncio.to_thread(self.status_sync)

    async def get(self, name: str) -> MetricEntry | None:
        return await asyncio.to_thread(self.get_sync, name)

    async def search(
        self, query: str, *, limit: int = 20, category: str | None = None
    ) -> list[SearchHit]:
        return await asyncio.to_thread(self.search_sync, query, limit=limit, category=category)


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()
