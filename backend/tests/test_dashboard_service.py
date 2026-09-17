from pathlib import Path

import pytest

from app.dashboard.layout import find_free_slot
from app.dashboard.models import (
    Dashboard,
    DashboardSettings,
    Layout,
    LayoutUpdate,
    PanelPlacement,
    TimeRange,
)
from app.dashboard.service import DashboardNotFoundError, DashboardService, PanelNotFoundError
from app.dashboard.store import DEFAULT_ID, DashboardStore
from app.panels import PanelValidationError, registry
from tests.conftest import TIMESERIES_SPEC


@pytest.fixture
def service(tmp_path: Path) -> DashboardService:
    return DashboardService(DashboardStore(tmp_path / "db" / "prompilot.sqlite"))


class TestStore:
    def test_empty_store_has_no_dashboards(self, tmp_path: Path) -> None:
        store = DashboardStore(tmp_path / "x.sqlite")
        assert store.load_sync(DEFAULT_ID) is None
        assert store.list_sync() == []

    def test_round_trip(self, tmp_path: Path) -> None:
        store = DashboardStore(tmp_path / "x.sqlite")
        spec = registry.validate(TIMESERIES_SPEC)
        dashboard = Dashboard(
            title="Prod",
            time_range=TimeRange(from_="now-6h", to="now"),
            refresh=None,
            panels=[PanelPlacement(spec=spec, layout=Layout(x=0, y=0, w=12, h=8))],
        )
        store.save_sync("prod", dashboard)
        assert DashboardStore(tmp_path / "x.sqlite").load_sync("prod") == dashboard
        summary = DashboardStore(tmp_path / "x.sqlite").list_sync()[0]
        assert (summary.id, summary.title, summary.panels) == ("prod", "Prod", 1)

    def test_single_dashboard_from_0_1_is_migrated(self, tmp_path: Path) -> None:
        import sqlite3

        path = tmp_path / "old.sqlite"
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE dashboard (id INTEGER PRIMARY KEY CHECK (id = 1), document TEXT NOT NULL,
                updated_at TEXT NOT NULL);
            INSERT INTO dashboard VALUES (1, '{"version": 1, "title": "Legacy", "timeRange":
                {"from": "now-1h", "to": "now"}, "refresh": "30s", "panels": []}',
                '2026-01-01T00:00:00+00:00');
            """
        )
        conn.commit()
        conn.close()
        store = DashboardStore(path)
        assert [d.id for d in store.list_sync()] == [DEFAULT_ID]
        loaded = store.load_sync(DEFAULT_ID)
        assert loaded is not None and loaded.title == "Legacy"


class TestService:
    async def test_add_panel_autoplaces_and_persists(self, service: DashboardService) -> None:
        first = await service.add_panel(DEFAULT_ID, TIMESERIES_SPEC)
        second = await service.add_panel(DEFAULT_ID, TIMESERIES_SPEC)
        third = await service.add_panel(DEFAULT_ID, TIMESERIES_SPEC)

        assert first.layout == Layout(x=0, y=0, w=12, h=8)
        assert second.layout == Layout(x=12, y=0, w=12, h=8)
        assert third.layout == Layout(x=0, y=8, w=12, h=8)
        dashboard = await service.get(DEFAULT_ID)
        assert [p.spec.id for p in dashboard.panels] == [
            first.spec.id,
            second.spec.id,
            third.spec.id,
        ]

    async def test_add_panel_with_explicit_layout(self, service: DashboardService) -> None:
        placement = await service.add_panel(DEFAULT_ID, TIMESERIES_SPEC, Layout(x=6, y=2, w=6, h=4))
        assert placement.layout == Layout(x=6, y=2, w=6, h=4)

    async def test_add_panel_rejects_invalid_spec(self, service: DashboardService) -> None:
        with pytest.raises(PanelValidationError):
            await service.add_panel(DEFAULT_ID, {**TIMESERIES_SPEC, "type": "nope"})
        assert (await service.get(DEFAULT_ID)).panels == []

    async def test_replace_panel_keeps_id_and_layout(self, service: DashboardService) -> None:
        placement = await service.add_panel(DEFAULT_ID, TIMESERIES_SPEC)
        updated = await service.replace_panel(
            DEFAULT_ID, placement.spec.id, {**TIMESERIES_SPEC, "title": "New", "id": "ignored"}
        )
        assert updated.spec.id == placement.spec.id
        assert updated.spec.title == "New"
        assert updated.layout == placement.layout

    async def test_patch_panel_merges_options(self, service: DashboardService) -> None:
        placement = await service.add_panel(
            DEFAULT_ID, {**TIMESERIES_SPEC, "options": {"fill": 0.5}}
        )
        patched = await service.patch_panel(
            DEFAULT_ID, placement.spec.id, {"title": "Bars", "options": {"draw": "bars"}}
        )
        assert patched.spec.title == "Bars"
        assert patched.spec.options["draw"] == "bars"
        assert patched.spec.options["fill"] == 0.5  # untouched option survives
        assert patched.spec.queries == placement.spec.queries

    async def test_patch_panel_validates_result(self, service: DashboardService) -> None:
        placement = await service.add_panel(DEFAULT_ID, TIMESERIES_SPEC)
        with pytest.raises(PanelValidationError, match="options.draw"):
            await service.patch_panel(
                DEFAULT_ID, placement.spec.id, {"options": {"draw": "spline"}}
            )

    async def test_remove_panel(self, service: DashboardService) -> None:
        placement = await service.add_panel(DEFAULT_ID, TIMESERIES_SPEC)
        await service.remove_panel(DEFAULT_ID, placement.spec.id)
        assert (await service.get(DEFAULT_ID)).panels == []
        with pytest.raises(PanelNotFoundError):
            await service.remove_panel(DEFAULT_ID, placement.spec.id)

    async def test_update_layout_ignores_unknown_ids(self, service: DashboardService) -> None:
        placement = await service.add_panel(DEFAULT_ID, TIMESERIES_SPEC)
        dashboard = await service.update_layout(
            DEFAULT_ID,
            [
                LayoutUpdate(id=placement.spec.id, layout=Layout(x=0, y=0, w=24, h=10)),
                LayoutUpdate(id="ghost", layout=Layout(x=0, y=0, w=1, h=1)),
            ],
        )
        assert dashboard.panels[0].layout == Layout(x=0, y=0, w=24, h=10)
        assert len(dashboard.panels) == 1

    async def test_update_settings(self, service: DashboardService) -> None:
        dashboard = await service.update_settings(
            DEFAULT_ID,
            DashboardSettings(
                title="Prod", time_range=TimeRange(from_="now-24h", to="now"), refresh="1m"
            ),
        )
        assert (dashboard.title, dashboard.time_range.from_, dashboard.refresh) == (
            "Prod",
            "now-24h",
            "1m",
        )

        dashboard = await service.update_settings(DEFAULT_ID, DashboardSettings(clear_refresh=True))
        assert dashboard.refresh is None
        assert dashboard.title == "Prod"  # untouched


class TestLayout:
    def test_fills_gaps_before_appending(self) -> None:
        spec = registry.validate(TIMESERIES_SPEC)
        panels = [
            PanelPlacement(spec=spec, layout=Layout(x=0, y=0, w=24, h=4)),
            PanelPlacement(spec=spec, layout=Layout(x=0, y=4, w=8, h=4)),
            PanelPlacement(spec=spec, layout=Layout(x=16, y=4, w=8, h=4)),
        ]
        assert find_free_slot(panels, 8, 4) == Layout(x=8, y=4, w=8, h=4)
        assert find_free_slot(panels, 12, 4) == Layout(x=0, y=8, w=12, h=4)

    def test_oversized_width_is_clamped(self) -> None:
        assert find_free_slot([], 99, 2) == Layout(x=0, y=0, w=24, h=2)


class TestDashboards:
    async def test_first_get_creates_the_default_dashboard(self, service: DashboardService) -> None:
        assert (await service.get(DEFAULT_ID)) == Dashboard()
        assert [d.id for d in await service.list()] == [DEFAULT_ID]
        with pytest.raises(DashboardNotFoundError):
            await service.get("nope")

    async def test_create_rename_delete(self, service: DashboardService) -> None:
        did, dashboard = await service.create("Payments SLOs")
        assert did == "payments-slos" and dashboard.title == "Payments SLOs"
        did2, _ = await service.create("Payments SLOs")
        assert did2 == "payments-slos-2"

        renamed = await service.update_settings(did, DashboardSettings(title="Payments"))
        assert renamed.title == "Payments"
        assert {d.id: d.title for d in await service.list()} == {
            DEFAULT_ID: "Overview",
            "payments-slos": "Payments",
            "payments-slos-2": "Payments SLOs",
        }

        await service.delete(did2)
        await service.delete(did)
        with pytest.raises(ValueError, match="at least one"):
            await service.delete(DEFAULT_ID)

    async def test_copy_dashboard_gets_fresh_panel_ids(self, service: DashboardService) -> None:
        original = await service.add_panel(DEFAULT_ID, TIMESERIES_SPEC)
        did, copy = await service.create("Copy", copy_from=DEFAULT_ID)
        assert len(copy.panels) == 1
        assert copy.panels[0].spec.id != original.spec.id
        assert copy.panels[0].spec.title == original.spec.title

    async def test_duplicate_panel(self, service: DashboardService) -> None:
        original = await service.add_panel(DEFAULT_ID, TIMESERIES_SPEC)
        dup = await service.duplicate_panel(DEFAULT_ID, original.spec.id)
        assert dup.spec.id != original.spec.id
        assert dup.spec.title == "CPU idle (copy)"
        assert dup.layout != original.layout
        assert len((await service.get(DEFAULT_ID)).panels) == 2
        with pytest.raises(PanelNotFoundError):
            await service.duplicate_panel(DEFAULT_ID, "ghost")
