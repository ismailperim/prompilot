"""SQLite table of projects. Lives in the main database file."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.projects.models import Project
from app.sqlite import connect, enable_wal

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    prometheus_url TEXT NOT NULL,
    prometheus_username TEXT,
    prometheus_password TEXT,
    tls_verify INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# Columns added after 0.2; applied when missing so older databases keep working.
_COLUMNS = {"tls_verify": "INTEGER NOT NULL DEFAULT 1"}


@dataclass(slots=True)
class ProjectRecord:
    """Full row including the secret; never leaves the backend."""

    slug: str
    name: str
    prometheus_url: str
    prometheus_username: str | None
    prometheus_password: str | None
    tls_verify: bool
    created_at: datetime
    updated_at: datetime

    def public(self) -> Project:
        return Project(
            slug=self.slug,
            name=self.name,
            prometheus_url=self.prometheus_url,
            prometheus_username=self.prometheus_username,
            has_password=bool(self.prometheus_password),
            tls_verify=self.tls_verify,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class ProjectStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._schema_ready = False

    def _connect(self) -> sqlite3.Connection:
        conn = connect(self.path)
        if not self._schema_ready:
            enable_wal(conn)
            conn.executescript(_SCHEMA)
            present = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
            for column, definition in _COLUMNS.items():
                if column not in present:
                    conn.execute(f"ALTER TABLE projects ADD COLUMN {column} {definition}")
            conn.commit()
            self._schema_ready = True
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _record(row: sqlite3.Row) -> ProjectRecord:
        return ProjectRecord(
            slug=row["slug"],
            name=row["name"],
            prometheus_url=row["prometheus_url"],
            prometheus_username=row["prometheus_username"],
            prometheus_password=row["prometheus_password"],
            tls_verify=bool(row["tls_verify"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def list_sync(self) -> list[ProjectRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at, slug").fetchall()
        return [self._record(r) for r in rows]

    def get_sync(self, slug: str) -> ProjectRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone()
        return self._record(row) if row else None

    def insert_sync(
        self,
        *,
        slug: str,
        name: str,
        prometheus_url: str,
        prometheus_username: str | None,
        prometheus_password: str | None,
        tls_verify: bool = True,
    ) -> ProjectRecord:
        now = datetime.now(tz=UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO projects (slug, name, prometheus_url, prometheus_username, "
                "prometheus_password, tls_verify, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    slug,
                    name,
                    prometheus_url,
                    prometheus_username,
                    prometheus_password,
                    int(tls_verify),
                    now,
                    now,
                ),
            )
        record = self.get_sync(slug)
        assert record is not None
        return record

    def update_sync(self, record: ProjectRecord) -> ProjectRecord:
        now = datetime.now(tz=UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE projects SET name = ?, prometheus_url = ?, prometheus_username = ?, "
                "prometheus_password = ?, tls_verify = ?, updated_at = ? WHERE slug = ?",
                (
                    record.name,
                    record.prometheus_url,
                    record.prometheus_username,
                    record.prometheus_password,
                    int(record.tls_verify),
                    now,
                    record.slug,
                ),
            )
        updated = self.get_sync(record.slug)
        assert updated is not None
        return updated

    def delete_sync(self, slug: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM projects WHERE slug = ?", (slug,))
        return cur.rowcount > 0

    async def list(self) -> list[ProjectRecord]:
        return await asyncio.to_thread(self.list_sync)

    async def get(self, slug: str) -> ProjectRecord | None:
        return await asyncio.to_thread(self.get_sync, slug)
