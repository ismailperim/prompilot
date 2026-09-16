"""Dashboard and panel CRUD."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, status
from fastapi.responses import Response

from app.api.deps import Dashboards
from app.dashboard.models import Dashboard, DashboardSettings, Layout, LayoutUpdate, PanelPlacement
from app.models import CamelModel
from app.panels import registry
from app.panels.base import PanelSpec

router = APIRouter(prefix="/api", tags=["dashboard"])


class NewPanel(CamelModel):
    spec: dict[str, Any]
    layout: Layout | None = None


class PanelTypeInfo(CamelModel):
    type: str
    description: str
    default_layout: tuple[int, int]
    options_schema: dict[str, Any]


@router.get("/dashboard", response_model=Dashboard)
async def get_dashboard(service: Dashboards) -> Dashboard:
    return await service.get()


@router.patch("/dashboard", response_model=Dashboard)
async def update_dashboard(settings: DashboardSettings, service: Dashboards) -> Dashboard:
    """Update title, time range and/or refresh interval."""
    return await service.update_settings(settings)


@router.put("/dashboard/layout", response_model=Dashboard)
async def update_layout(updates: list[LayoutUpdate], service: Dashboards) -> Dashboard:
    """Persist grid positions after drag/resize. Unknown ids are ignored."""
    return await service.update_layout(updates)


@router.get("/panels/types", response_model=list[PanelTypeInfo])
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


@router.post("/panels", response_model=PanelPlacement, status_code=status.HTTP_201_CREATED)
async def add_panel(body: NewPanel, service: Dashboards) -> PanelPlacement:
    """Add a panel. ``spec.id`` is generated when omitted; layout is auto-placed when omitted."""
    return await service.add_panel(body.spec, body.layout)


@router.put("/panels/{panel_id}", response_model=PanelPlacement)
async def replace_panel(
    panel_id: str, spec: Annotated[dict[str, Any], Body()], service: Dashboards
) -> PanelPlacement:
    return await service.replace_panel(panel_id, spec)


@router.patch("/panels/{panel_id}", response_model=PanelPlacement)
async def patch_panel(
    panel_id: str, changes: Annotated[dict[str, Any], Body()], service: Dashboards
) -> PanelPlacement:
    """Shallow-merge changes into the spec; ``options`` merges one level deeper."""
    return await service.patch_panel(panel_id, changes)


@router.delete("/panels/{panel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_panel(panel_id: str, service: Dashboards) -> Response:
    await service.remove_panel(panel_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/panels/validate", response_model=PanelSpec)
async def validate_panel(spec: Annotated[dict[str, Any], Body()]) -> PanelSpec:
    """Validate a spec without saving it; returns the normalised spec or 422."""
    return registry.validate(spec)
