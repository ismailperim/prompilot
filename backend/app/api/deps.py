"""FastAPI dependencies shared by routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.prometheus import PrometheusClient


def get_prometheus(request: Request) -> PrometheusClient:
    return request.app.state.prometheus


Prometheus = Annotated[PrometheusClient, Depends(get_prometheus)]
AppSettings = Annotated[Settings, Depends(get_settings)]
