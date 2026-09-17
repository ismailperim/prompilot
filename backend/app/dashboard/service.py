"""Read-modify-write operations on a project's dashboards. All mutations go through here."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from uuid import uuid4

from app.dashboard.layout import find_free_slot
from app.dashboard.models import (
    Dashboard,
    DashboardSettings,
    Layout,
    LayoutUpdate,
    PanelPlacement,
)
from app.dashboard.store import DEFAULT_ID, DashboardStore, DashboardSummary
from app.panels import PanelSpec, registry


class PanelNotFoundError(KeyError):
    def __init__(self, panel_id: str) -> None:
        super().__init__(panel_id)
        self.panel_id = panel_id

    def __str__(self) -> str:
        return f"panel {self.panel_id!r} not found"


class DashboardNotFoundError(KeyError):
    def __init__(self, dashboard_id: str) -> None:
        super().__init__(dashboard_id)
        self.dashboard_id = dashboard_id

    def __str__(self) -> str:
        return f"dashboard {self.dashboard_id!r} not found"


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-")
    return slug or "dashboard"


class DashboardService:
    def __init__(self, store: DashboardStore) -> None:
        self._store = store
        self._lock = asyncio.Lock()

    # ---- dashboards ---------------------------------------------------------

    async def list(self) -> list[DashboardSummary]:
        summaries = await self._store.list()
        if summaries:
            return summaries
        # A project always has at least one dashboard.
        await self._store.save(DEFAULT_ID, Dashboard())
        return await self._store.list()

    async def get(self, dashboard_id: str) -> Dashboard:
        dashboard = await self._store.load(dashboard_id)
        if dashboard is None:
            if dashboard_id == DEFAULT_ID and not await self._store.list():
                dashboard = Dashboard()
                await self._store.save(DEFAULT_ID, dashboard)
                return dashboard
            raise DashboardNotFoundError(dashboard_id)
        return dashboard

    async def create(self, title: str, *, copy_from: str | None = None) -> tuple[str, Dashboard]:
        await self.list()  # makes sure the default dashboard exists before others are added
        async with self._lock:
            base = slugify(title)
            dashboard_id = base
            n = 2
            while await self._store.exists(dashboard_id):
                dashboard_id = f"{base}-{n}"
                n += 1
            if copy_from:
                source = await self._store.load(copy_from)
                if source is None:
                    raise DashboardNotFoundError(copy_from)
                dashboard = source.model_copy(deep=True)
                for placement in dashboard.panels:
                    placement.spec = placement.spec.model_copy(update={"id": str(uuid4())})
                dashboard.title = title.strip()
            else:
                dashboard = Dashboard(title=title.strip())
            await self._store.save(dashboard_id, dashboard)
            return dashboard_id, dashboard

    async def delete(self, dashboard_id: str) -> None:
        async with self._lock:
            if len(await self._store.list()) <= 1:
                raise ValueError("a project keeps at least one dashboard")
            if not await self._store.delete(dashboard_id):
                raise DashboardNotFoundError(dashboard_id)

    # ---- settings & layout ----------------------------------------------------

    async def update_settings(self, dashboard_id: str, settings: DashboardSettings) -> Dashboard:
        async with self._lock:
            dashboard = await self.get(dashboard_id)
            if settings.title is not None:
                dashboard.title = settings.title
            if settings.time_range is not None:
                dashboard.time_range = settings.time_range
            if settings.clear_refresh:
                dashboard.refresh = None
            elif settings.refresh is not None:
                dashboard.refresh = settings.refresh
            await self._store.save(dashboard_id, dashboard)
            return dashboard

    async def update_layout(self, dashboard_id: str, updates: list[LayoutUpdate]) -> Dashboard:
        async with self._lock:
            dashboard = await self.get(dashboard_id)
            by_id = {u.id: u.layout for u in updates}
            for placement in dashboard.panels:
                if placement.spec.id in by_id:
                    placement.layout = by_id[placement.spec.id]
            await self._store.save(dashboard_id, dashboard)
            return dashboard

    # ---- panels ---------------------------------------------------------------

    async def add_panel(
        self,
        dashboard_id: str,
        spec_data: dict[str, Any] | PanelSpec,
        layout: Layout | None = None,
    ) -> PanelPlacement:
        spec = registry.validate(spec_data)
        async with self._lock:
            dashboard = await self.get(dashboard_id)
            if dashboard.find(spec.id) is not None:
                raise ValueError(f"panel {spec.id!r} already exists")
            if layout is None:
                w, h = registry.get(spec.type).default_layout
                layout = find_free_slot(dashboard.panels, w, h)
            placement = PanelPlacement(spec=spec, layout=layout)
            dashboard.panels.append(placement)
            await self._store.save(dashboard_id, dashboard)
            return placement

    async def duplicate_panel(self, dashboard_id: str, panel_id: str) -> PanelPlacement:
        async with self._lock:
            dashboard = await self.get(dashboard_id)
            source = dashboard.find(panel_id)
            if source is None:
                raise PanelNotFoundError(panel_id)
            spec = source.spec.model_copy(
                update={"id": str(uuid4()), "title": f"{source.spec.title} (copy)"}
            )
            layout = find_free_slot(dashboard.panels, source.layout.w, source.layout.h)
            placement = PanelPlacement(spec=spec, layout=layout)
            dashboard.panels.append(placement)
            await self._store.save(dashboard_id, dashboard)
            return placement

    async def replace_panel(
        self, dashboard_id: str, panel_id: str, spec_data: dict[str, Any]
    ) -> PanelPlacement:
        spec = registry.validate({**spec_data, "id": panel_id})
        async with self._lock:
            dashboard = await self.get(dashboard_id)
            placement = dashboard.find(panel_id)
            if placement is None:
                raise PanelNotFoundError(panel_id)
            placement.spec = spec
            await self._store.save(dashboard_id, dashboard)
            return placement

    async def patch_panel(
        self, dashboard_id: str, panel_id: str, changes: dict[str, Any]
    ) -> PanelPlacement:
        """Shallow-merge ``changes`` into the spec (``options`` merges one level deeper)."""
        async with self._lock:
            dashboard = await self.get(dashboard_id)
            placement = dashboard.find(panel_id)
            if placement is None:
                raise PanelNotFoundError(panel_id)
            current = placement.spec.model_dump(by_alias=True)
            merged = {**current, **changes, "id": panel_id}
            if "options" in changes and isinstance(changes["options"], dict):
                merged["options"] = {**current["options"], **changes["options"]}
            placement.spec = registry.validate(merged)
            await self._store.save(dashboard_id, dashboard)
            return placement

    async def remove_panel(self, dashboard_id: str, panel_id: str) -> None:
        async with self._lock:
            dashboard = await self.get(dashboard_id)
            if dashboard.find(panel_id) is None:
                raise PanelNotFoundError(panel_id)
            dashboard.panels = [p for p in dashboard.panels if p.spec.id != panel_id]
            await self._store.save(dashboard_id, dashboard)
