"""Dashboards and their panels."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, status
from fastapi.responses import Response
from pydantic import Field

from app.api.deps import DashboardId, Dashboards, Runtime
from app.dashboard.models import Dashboard, DashboardSettings, Layout, LayoutUpdate, PanelPlacement
from app.dashboard.service import DashboardNotFoundError
from app.models import CamelModel
from app.panels import registry
from app.panels.base import PanelSpec

router = APIRouter(prefix="/api/projects/{slug}", tags=["dashboard"])
global_router = APIRouter(prefix="/api", tags=["panels"])


class NewPanel(CamelModel):
    spec: dict[str, Any]
    layout: Layout | None = None


class PanelTypeInfo(CamelModel):
    type: str
    description: str
    default_layout: tuple[int, int]
    options_schema: dict[str, Any]


class DashboardSummaryOut(CamelModel):
    id: str
    title: str
    panels: int
    updated_at: datetime


class DashboardCreate(CamelModel):
    title: str = Field(min_length=1, max_length=120)
    copy_from: str | None = Field(default=None, description="Duplicate this dashboard's panels")


class DashboardOut(CamelModel):
    id: str
    dashboard: Dashboard


# ---- dashboards -------------------------------------------------------------


@router.get("/dashboards", response_model=list[DashboardSummaryOut])
async def list_dashboards(service: Dashboards) -> list[DashboardSummaryOut]:
    return [
        DashboardSummaryOut(id=d.id, title=d.title, panels=d.panels, updated_at=d.updated_at)
        for d in await service.list()
    ]


@router.post("/dashboards", response_model=DashboardOut, status_code=status.HTTP_201_CREATED)
async def create_dashboard(body: DashboardCreate, service: Dashboards) -> DashboardOut:
    try:
        dashboard_id, dashboard = await service.create(body.title, copy_from=body.copy_from)
    except DashboardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DashboardOut(id=dashboard_id, dashboard=dashboard)


@router.get("/dashboards/{did}", response_model=Dashboard)
async def get_dashboard(did: DashboardId, service: Dashboards) -> Dashboard:
    return await service.get(did)


@router.patch("/dashboards/{did}", response_model=Dashboard)
async def update_dashboard(
    did: DashboardId, settings: DashboardSettings, service: Dashboards
) -> Dashboard:
    """Update title, time range and/or refresh interval."""
    return await service.update_settings(did, settings)


@router.delete("/dashboards/{did}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dashboard(did: DashboardId, runtime: Runtime) -> Response:
    try:
        await runtime.dashboard.delete(did)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await runtime.chat.clear(did)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/dashboards/{did}/layout", response_model=Dashboard)
async def update_layout(
    did: DashboardId, updates: list[LayoutUpdate], service: Dashboards
) -> Dashboard:
    """Persist grid positions after drag/resize. Unknown ids are ignored."""
    return await service.update_layout(did, updates)


# ---- panels -----------------------------------------------------------------


@global_router.get("/panels/types", response_model=list[PanelTypeInfo])
async def panel_types() -> list[PanelTypeInfo]:
    """Registered panel types with their options schema (for UIs and the agent)."""
    return [
        PanelTypeInfo(
            type=m.type,
            description=m.description,
            default_layout=m.default_layout,
            options_schema=m.options_model.model_json_schema(by_alias=True),
        )
        for m in registry.modules()
    ]


@global_router.post("/panels/validate", response_model=PanelSpec)
async def validate_panel(spec: Annotated[dict[str, Any], Body()]) -> PanelSpec:
    """Validate a spec without saving it; returns the normalised spec or 422."""
    return registry.validate(spec)


@router.post(
    "/dashboards/{did}/panels", response_model=PanelPlacement, status_code=status.HTTP_201_CREATED
)
async def add_panel(did: DashboardId, body: NewPanel, service: Dashboards) -> PanelPlacement:
    """Add a panel. ``spec.id`` is generated when omitted; layout is auto-placed when omitted."""
    return await service.add_panel(did, body.spec, body.layout)


@router.post(
    "/dashboards/{did}/panels/{panel_id}/duplicate",
    response_model=PanelPlacement,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_panel(did: DashboardId, panel_id: str, service: Dashboards) -> PanelPlacement:
    return await service.duplicate_panel(did, panel_id)


@router.put("/dashboards/{did}/panels/{panel_id}", response_model=PanelPlacement)
async def replace_panel(
    did: DashboardId, panel_id: str, spec: Annotated[dict[str, Any], Body()], service: Dashboards
) -> PanelPlacement:
    return await service.replace_panel(did, panel_id, spec)


@router.patch("/dashboards/{did}/panels/{panel_id}", response_model=PanelPlacement)
async def patch_panel(
    did: DashboardId,
    panel_id: str,
    changes: Annotated[dict[str, Any], Body()],
    service: Dashboards,
) -> PanelPlacement:
    """Shallow-merge changes into the spec; ``options`` merges one level deeper."""
    return await service.patch_panel(did, panel_id, changes)


@router.delete("/dashboards/{did}/panels/{panel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_panel(did: DashboardId, panel_id: str, service: Dashboards) -> Response:
    await service.remove_panel(did, panel_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
