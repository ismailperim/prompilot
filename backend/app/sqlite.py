"""Shared SQLite connection helpers."""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

BUSY_TIMEOUT_SECONDS = 30


def connect(path: Path) -> sqlite3.Connection:
    """Open the file with a generous busy timeout: builds write while the UI polls."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path, timeout=BUSY_TIMEOUT_SECONDS)


def enable_wal(conn: sqlite3.Connection) -> None:
    """Switch the file to WAL once.

    Changing the journal mode needs an exclusive lock, so the call fails when another
    connection is busy. WAL is persistent in the file, so whoever got there first has
    already done the job and the failure can be ignored.
    """
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("PRAGMA journal_mode=WAL")
