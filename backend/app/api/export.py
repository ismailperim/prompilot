"""Download the dashboard in external formats."""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import DashboardId, Dashboards
from app.export.grafana import export_dashboard, slugify

router = APIRouter(prefix="/api/projects/{slug}/dashboards/{did}/export", tags=["export"])


@router.get("/grafana")
async def grafana(did: DashboardId, service: Dashboards, download: bool = True) -> Response:
    """Grafana dashboard JSON, ready for *Dashboards → New → Import*."""
    dashboard = await service.get(did)
    body = json.dumps(export_dashboard(dashboard), indent=2)
    headers = {}
    if download:
        headers["Content-Disposition"] = (
            f'attachment; filename="{slugify(dashboard.title)}.grafana.json"'
        )
    return Response(content=body, media_type="application/json", headers=headers)
