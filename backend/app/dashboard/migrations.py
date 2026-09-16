"""Version migrations for persisted specs and dashboards.

Every schema change bumps the relevant ``*_VERSION`` constant and adds a
function ``n → n+1`` to the matching table. Stored documents are migrated
on load, so old data never has to be edited by hand.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.dashboard.models import DASHBOARD_VERSION
from app.panels.base import SPEC_VERSION

Migration = Callable[[dict[str, Any]], dict[str, Any]]

# {from_version: migration}. Empty until the first schema change.
SPEC_MIGRATIONS: dict[int, Migration] = {}
DASHBOARD_MIGRATIONS: dict[int, Migration] = {}


class MigrationError(RuntimeError):
    pass


def _migrate(
    document: dict[str, Any], *, target: int, table: dict[int, Migration], kind: str
) -> dict[str, Any]:
    version = int(document.get("version", 1))
    if version > target:
        raise MigrationError(
            f"{kind} version {version} is newer than this build supports ({target}); "
            "upgrade PromPilot"
        )
    while version < target:
        migration = table.get(version)
        if migration is None:
            raise MigrationError(f"no {kind} migration from version {version} to {version + 1}")
        document = migration(dict(document))
        version += 1
    return {**document, "version": version}


def migrate_spec(spec: dict[str, Any]) -> dict[str, Any]:
    return _migrate(spec, target=SPEC_VERSION, table=SPEC_MIGRATIONS, kind="panel spec")


def migrate_dashboard(dashboard: dict[str, Any]) -> dict[str, Any]:
    dashboard = _migrate(
        dashboard, target=DASHBOARD_VERSION, table=DASHBOARD_MIGRATIONS, kind="dashboard"
    )
    for placement in dashboard.get("panels", []):
        placement["spec"] = migrate_spec(placement["spec"])
    return dashboard
