"""Read-modify-write operations on the dashboard. All mutations go through here."""

from __future__ import annotations

import asyncio
from typing import Any

from app.dashboard.layout import find_free_slot
from app.dashboard.models import (
    Dashboard,
    DashboardSettings,
    Layout,
    LayoutUpdate,
    PanelPlacement,
)
from app.dashboard.store import DashboardStore
from app.panels import PanelSpec, registry


class PanelNotFoundError(KeyError):
    def __init__(self, panel_id: str) -> None:
        super().__init__(panel_id)
        self.panel_id = panel_id

    def __str__(self) -> str:
        return f"panel {self.panel_id!r} not found"


class DashboardService:
    def __init__(self, store: DashboardStore) -> None:
        self._store = store
        self._lock = asyncio.Lock()

    async def get(self) -> Dashboard:
        return await self._store.load()

    async def update_settings(self, settings: DashboardSettings) -> Dashboard:
        async with self._lock:
            dashboard = await self._store.load()
            if settings.title is not None:
                dashboard.title = settings.title
            if settings.time_range is not None:
                dashboard.time_range = settings.time_range
            if settings.clear_refresh:
                dashboard.refresh = None
            elif settings.refresh is not None:
                dashboard.refresh = settings.refresh
            await self._store.save(dashboard)
            return dashboard

    async def add_panel(
        self, spec_data: dict[str, Any] | PanelSpec, layout: Layout | None = None
    ) -> PanelPlacement:
        spec = registry.validate(spec_data)
        async with self._lock:
            dashboard = await self._store.load()
            if dashboard.find(spec.id) is not None:
                raise ValueError(f"panel {spec.id!r} already exists")
            if layout is None:
                w, h = registry.get(spec.type).default_layout
                layout = find_free_slot(dashboard.panels, w, h)
            placement = PanelPlacement(spec=spec, layout=layout)
            dashboard.panels.append(placement)
            await self._store.save(dashboard)
            return placement

    async def replace_panel(self, panel_id: str, spec_data: dict[str, Any]) -> PanelPlacement:
        spec = registry.validate({**spec_data, "id": panel_id})
        async with self._lock:
            dashboard = await self._store.load()
            placement = dashboard.find(panel_id)
            if placement is None:
                raise PanelNotFoundError(panel_id)
            placement.spec = spec
            await self._store.save(dashboard)
            return placement

    async def patch_panel(self, panel_id: str, changes: dict[str, Any]) -> PanelPlacement:
        """Shallow-merge ``changes`` into the spec (``options`` merges one level deeper)."""
        async with self._lock:
            dashboard = await self._store.load()
            placement = dashboard.find(panel_id)
            if placement is None:
                raise PanelNotFoundError(panel_id)
            current = placement.spec.model_dump(by_alias=True)
            merged = {**current, **changes, "id": panel_id}
            if "options" in changes and isinstance(changes["options"], dict):
                merged["options"] = {**current["options"], **changes["options"]}
            placement.spec = registry.validate(merged)
            await self._store.save(dashboard)
            return placement

    async def remove_panel(self, panel_id: str) -> None:
        async with self._lock:
            dashboard = await self._store.load()
            if dashboard.find(panel_id) is None:
                raise PanelNotFoundError(panel_id)
            dashboard.panels = [p for p in dashboard.panels if p.spec.id != panel_id]
            await self._store.save(dashboard)

    async def update_layout(self, updates: list[LayoutUpdate]) -> Dashboard:
        async with self._lock:
            dashboard = await self._store.load()
            by_id = {u.id: u.layout for u in updates}
            for placement in dashboard.panels:
                if placement.spec.id in by_id:
                    placement.layout = by_id[placement.spec.id]
            await self._store.save(dashboard)
            return dashboard
