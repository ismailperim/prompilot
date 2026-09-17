"""Panel data: run each panel's queries for a time range and return frames."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import AppSettings, Dashboards, Prometheus
from app.dashboard.data import PanelData, fetch_panel_data
from app.dashboard.models import TimeRange
from app.dashboard.timerange import resolve, to_millis
from app.models import CamelModel

router = APIRouter(prefix="/api/projects/{slug}", tags=["data"])


class DataRequest(CamelModel):
    ids: list[str] | None = None
    time_range: TimeRange | None = None


class DataResponse(CamelModel):
    time_range: dict[str, int]
    panels: dict[str, PanelData]


@router.post("/panels/data", response_model=DataResponse)
async def panels_data(
    body: DataRequest, service: Dashboards, prometheus: Prometheus, settings: AppSettings
) -> DataResponse:
    """Batch fetch. Defaults to every panel and the dashboard's own time range."""
    dashboard = await service.get()
    time_range = body.time_range or dashboard.time_range
    start, end = resolve(time_range)

    placements = dashboard.panels
    if body.ids is not None:
        wanted = set(body.ids)
        placements = [p for p in placements if p.spec.id in wanted]

    results = await asyncio.gather(
        *(
            fetch_panel_data(
                prometheus, p.spec, start, end, max_data_points=settings.prometheus_max_data_points
            )
            for p in placements
        )
    )
    return DataResponse(
        time_range={"from": to_millis(start), "to": to_millis(end)},
        panels={p.spec.id: data for p, data in zip(placements, results, strict=True)},
    )


@router.get("/panels/{panel_id}/data", response_model=PanelData)
async def panel_data(
    panel_id: str,
    service: Dashboards,
    prometheus: Prometheus,
    settings: AppSettings,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
) -> PanelData:
    dashboard = await service.get()
    placement = dashboard.find(panel_id)
    if placement is None:
        raise HTTPException(status_code=404, detail=f"panel {panel_id!r} not found")
    time_range = dashboard.time_range
    if from_ or to:
        time_range = TimeRange(from_=from_ or time_range.from_, to=to or time_range.to)
    start, end = resolve(time_range)
    return await fetch_panel_data(
        prometheus, placement.spec, start, end, max_data_points=settings.prometheus_max_data_points
    )
