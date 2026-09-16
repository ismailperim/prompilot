from typing import Any

import pytest

from app.dashboard import migrations
from app.dashboard.migrations import MigrationError, migrate_dashboard, migrate_spec


def test_current_version_is_untouched() -> None:
    spec = {"version": 1, "type": "timeseries"}
    assert migrate_spec(spec) == spec


def test_missing_version_is_treated_as_1() -> None:
    assert migrate_spec({"type": "timeseries"})["version"] == 1


def test_newer_version_is_rejected() -> None:
    with pytest.raises(MigrationError, match="newer"):
        migrate_spec({"version": 99})


def test_chain_of_migrations_is_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    def v1_to_v2(doc: dict[str, Any]) -> dict[str, Any]:
        doc["renamed"] = doc.pop("old")
        return doc

    def v2_to_v3(doc: dict[str, Any]) -> dict[str, Any]:
        doc["added"] = True
        return doc

    monkeypatch.setattr(migrations, "SPEC_VERSION", 3)
    monkeypatch.setattr(migrations, "SPEC_MIGRATIONS", {1: v1_to_v2, 2: v2_to_v3})

    result = migrate_spec({"version": 1, "old": "x"})
    assert result == {"version": 3, "renamed": "x", "added": True}


def test_gap_in_chain_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(migrations, "SPEC_VERSION", 3)
    monkeypatch.setattr(migrations, "SPEC_MIGRATIONS", {1: lambda d: d})
    with pytest.raises(MigrationError, match="from version 2 to 3"):
        migrate_spec({"version": 1})


def test_dashboard_migration_recurses_into_specs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(migrations, "SPEC_VERSION", 2)
    monkeypatch.setattr(migrations, "SPEC_MIGRATIONS", {1: lambda d: {**d, "touched": True}})
    doc = {"version": 1, "panels": [{"spec": {"version": 1}, "layout": {}}]}
    result = migrate_dashboard(doc)
    assert result["panels"][0]["spec"] == {"version": 2, "touched": True}
