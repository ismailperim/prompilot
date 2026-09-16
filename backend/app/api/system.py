"""System-level endpoints: connectivity status for the UI."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import AppSettings, Prometheus
from app.prometheus import PrometheusError

router = APIRouter(prefix="/api", tags=["system"])


class PrometheusStatus(BaseModel):
    url: str
    reachable: bool
    version: str | None = None
    error: str | None = None


class LLMStatus(BaseModel):
    enabled: bool
    model: str | None = None


class SystemStatus(BaseModel):
    prometheus: PrometheusStatus
    llm: LLMStatus


@router.get("/status", response_model=SystemStatus)
async def status(prometheus: Prometheus, settings: AppSettings) -> SystemStatus:
    """Report whether Prometheus is reachable and whether an LLM is configured."""
    try:
        info = await prometheus.build_info()
        prom = PrometheusStatus(
            url=prometheus.base_url, reachable=True, version=info.get("version")
        )
    except PrometheusError as exc:
        prom = PrometheusStatus(url=prometheus.base_url, reachable=False, error=str(exc))

    return SystemStatus(
        prometheus=prom,
        llm=LLMStatus(enabled=settings.llm_enabled, model=settings.llm_model),
    )
