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
from app.dashboard.service import DashboardService, PanelNotFoundError
from app.dashboard.store import DashboardStore
from app.panels import PanelValidationError, registry
from tests.conftest import TIMESERIES_SPEC


@pytest.fixture
def service(tmp_path: Path) -> DashboardService:
    return DashboardService(DashboardStore(tmp_path / "db" / "prompilot.sqlite"))


class TestStore:
    def test_empty_store_yields_default_dashboard(self, tmp_path: Path) -> None:
        store = DashboardStore(tmp_path / "x.sqlite")
        dashboard = store.load_sync()
        assert dashboard == Dashboard()

    def test_round_trip(self, tmp_path: Path) -> None:
        store = DashboardStore(tmp_path / "x.sqlite")
        spec = registry.validate(TIMESERIES_SPEC)
        dashboard = Dashboard(
            title="Prod",
            time_range=TimeRange(from_="now-6h", to="now"),
            refresh=None,
            panels=[PanelPlacement(spec=spec, layout=Layout(x=0, y=0, w=12, h=8))],
        )
        store.save_sync(dashboard)
        assert DashboardStore(tmp_path / "x.sqlite").load_sync() == dashboard


class TestService:
    async def test_add_panel_autoplaces_and_persists(self, service: DashboardService) -> None:
        first = await service.add_panel(TIMESERIES_SPEC)
        second = await service.add_panel(TIMESERIES_SPEC)
        third = await service.add_panel(TIMESERIES_SPEC)

        assert first.layout == Layout(x=0, y=0, w=12, h=8)
        assert second.layout == Layout(x=12, y=0, w=12, h=8)
        assert third.layout == Layout(x=0, y=8, w=12, h=8)
        dashboard = await service.get()
        assert [p.spec.id for p in dashboard.panels] == [
            first.spec.id,
            second.spec.id,
            third.spec.id,
        ]

    async def test_add_panel_with_explicit_layout(self, service: DashboardService) -> None:
        placement = await service.add_panel(TIMESERIES_SPEC, Layout(x=6, y=2, w=6, h=4))
        assert placement.layout == Layout(x=6, y=2, w=6, h=4)

    async def test_add_panel_rejects_invalid_spec(self, service: DashboardService) -> None:
        with pytest.raises(PanelValidationError):
            await service.add_panel({**TIMESERIES_SPEC, "type": "nope"})
        assert (await service.get()).panels == []

    async def test_replace_panel_keeps_id_and_layout(self, service: DashboardService) -> None:
        placement = await service.add_panel(TIMESERIES_SPEC)
        updated = await service.replace_panel(
            placement.spec.id, {**TIMESERIES_SPEC, "title": "New", "id": "ignored"}
        )
        assert updated.spec.id == placement.spec.id
        assert updated.spec.title == "New"
        assert updated.layout == placement.layout

    async def test_patch_panel_merges_options(self, service: DashboardService) -> None:
        placement = await service.add_panel({**TIMESERIES_SPEC, "options": {"fill": 0.5}})
        patched = await service.patch_panel(
            placement.spec.id, {"title": "Bars", "options": {"draw": "bars"}}
        )
        assert patched.spec.title == "Bars"
        assert patched.spec.options["draw"] == "bars"
        assert patched.spec.options["fill"] == 0.5  # untouched option survives
        assert patched.spec.queries == placement.spec.queries

    async def test_patch_panel_validates_result(self, service: DashboardService) -> None:
        placement = await service.add_panel(TIMESERIES_SPEC)
        with pytest.raises(PanelValidationError, match="options.draw"):
            await service.patch_panel(placement.spec.id, {"options": {"draw": "spline"}})

    async def test_remove_panel(self, service: DashboardService) -> None:
        placement = await service.add_panel(TIMESERIES_SPEC)
        await service.remove_panel(placement.spec.id)
        assert (await service.get()).panels == []
        with pytest.raises(PanelNotFoundError):
            await service.remove_panel(placement.spec.id)

    async def test_update_layout_ignores_unknown_ids(self, service: DashboardService) -> None:
        placement = await service.add_panel(TIMESERIES_SPEC)
        dashboard = await service.update_layout(
            [
                LayoutUpdate(id=placement.spec.id, layout=Layout(x=0, y=0, w=24, h=10)),
                LayoutUpdate(id="ghost", layout=Layout(x=0, y=0, w=1, h=1)),
            ]
        )
        assert dashboard.panels[0].layout == Layout(x=0, y=0, w=24, h=10)
        assert len(dashboard.panels) == 1

    async def test_update_settings(self, service: DashboardService) -> None:
        dashboard = await service.update_settings(
            DashboardSettings(
                title="Prod", time_range=TimeRange(from_="now-24h", to="now"), refresh="1m"
            )
        )
        assert (dashboard.title, dashboard.time_range.from_, dashboard.refresh) == (
            "Prod",
            "now-24h",
            "1m",
        )

        dashboard = await service.update_settings(DashboardSettings(clear_refresh=True))
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
