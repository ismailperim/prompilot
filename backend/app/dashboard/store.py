"""SQLite persistence for a project's dashboards."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.dashboard.migrations import migrate_dashboard
from app.dashboard.models import Dashboard
from app.sqlite import connect, enable_wal

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dashboards (
    id TEXT PRIMARY KEY,
    document TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

DEFAULT_ID = "overview"


@dataclass(slots=True, frozen=True)
class DashboardSummary:
    id: str
    title: str
    panels: int
    updated_at: datetime


class DashboardStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._schema_ready = False

    def _connect(self) -> sqlite3.Connection:
        conn = connect(self.path)
        if not self._schema_ready:
            enable_wal(conn)
            conn.executescript(_SCHEMA)
            self._migrate_single_dashboard(conn)
            self._schema_ready = True
        return conn

    @staticmethod
    def _migrate_single_dashboard(conn: sqlite3.Connection) -> None:
        """0.1 kept one dashboard in a one-row table; move it into the list as 'overview'."""
        legacy = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'dashboard'"
        ).fetchone()
        if legacy is None:
            return
        row = conn.execute("SELECT document, updated_at FROM dashboard WHERE id = 1").fetchone()
        if row and conn.execute("SELECT COUNT(*) FROM dashboards").fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO dashboards (id, document, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (DEFAULT_ID, row[0], row[1], row[1]),
            )
        conn.execute("DROP TABLE dashboard")

    # ---- sync ---------------------------------------------------------------

    def list_sync(self) -> list[DashboardSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, document, updated_at FROM dashboards ORDER BY created_at, id"
            ).fetchall()
        out = []
        for id_, document, updated in rows:
            doc = json.loads(document)
            out.append(
                DashboardSummary(
                    id=id_,
                    title=doc.get("title", id_),
                    panels=len(doc.get("panels", [])),
                    updated_at=datetime.fromisoformat(updated),
                )
            )
        return out

    def load_sync(self, dashboard_id: str) -> Dashboard | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT document FROM dashboards WHERE id = ?", (dashboard_id,)
            ).fetchone()
        if row is None:
            return None
        return Dashboard.model_validate(migrate_dashboard(json.loads(row[0])))

    def save_sync(self, dashboard_id: str, dashboard: Dashboard) -> None:
        document = dashboard.model_dump_json(by_alias=True)
        now = datetime.now(tz=UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO dashboards (id, document, created_at, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET document = excluded.document, "
                "updated_at = excluded.updated_at",
                (dashboard_id, document, now, now),
            )

    def delete_sync(self, dashboard_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM dashboards WHERE id = ?", (dashboard_id,))
        return cur.rowcount > 0

    def exists_sync(self, dashboard_id: str) -> bool:
        with self._connect() as conn:
            return (
                conn.execute("SELECT 1 FROM dashboards WHERE id = ?", (dashboard_id,)).fetchone()
                is not None
            )

    # ---- async --------------------------------------------------------------

    async def list(self) -> list[DashboardSummary]:
        return await asyncio.to_thread(self.list_sync)

    async def load(self, dashboard_id: str) -> Dashboard | None:
        return await asyncio.to_thread(self.load_sync, dashboard_id)

    async def save(self, dashboard_id: str, dashboard: Dashboard) -> None:
        await asyncio.to_thread(self.save_sync, dashboard_id, dashboard)

    async def delete(self, dashboard_id: str) -> bool:
        return await asyncio.to_thread(self.delete_sync, dashboard_id)

    async def exists(self, dashboard_id: str) -> bool:
        return await asyncio.to_thread(self.exists_sync, dashboard_id)
