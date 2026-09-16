"""SQLite persistence for the (single, for now) dashboard."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.dashboard.migrations import migrate_dashboard
from app.dashboard.models import Dashboard

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dashboard (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    document TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class DashboardStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        return conn

    def load_sync(self) -> Dashboard:
        with self._connect() as conn:
            row = conn.execute("SELECT document FROM dashboard WHERE id = 1").fetchone()
        if row is None:
            return Dashboard()
        return Dashboard.model_validate(migrate_dashboard(json.loads(row[0])))

    def save_sync(self, dashboard: Dashboard) -> None:
        document = dashboard.model_dump_json(by_alias=True)
        now = datetime.now(tz=UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO dashboard (id, document, updated_at) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET document = excluded.document, "
                "updated_at = excluded.updated_at",
                (document, now),
            )

    async def load(self) -> Dashboard:
        return await asyncio.to_thread(self.load_sync)

    async def save(self, dashboard: Dashboard) -> None:
        await asyncio.to_thread(self.save_sync, dashboard)
