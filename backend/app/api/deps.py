"""FastAPI dependencies shared by routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.dashboard.service import DashboardService
from app.prometheus import PrometheusClient


def get_prometheus(request: Request) -> PrometheusClient:
    return request.app.state.prometheus


def get_dashboard_service(request: Request) -> DashboardService:
    return request.app.state.dashboard


Prometheus = Annotated[PrometheusClient, Depends(get_prometheus)]
Dashboards = Annotated[DashboardService, Depends(get_dashboard_service)]
AppSettings = Annotated[Settings, Depends(get_settings)]
