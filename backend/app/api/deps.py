"""FastAPI dependencies shared by routers.

Project-scoped routers are mounted under ``/api/projects/{slug}``; ``get_runtime``
resolves the slug to that project's runtime (Prometheus client, dashboard,
catalog, knowledge) or raises 404.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.catalog.builder import CatalogBuilder
from app.catalog.store import CatalogStore
from app.config import Settings, get_settings
from app.dashboard.service import DashboardService
from app.knowledge.service import KnowledgeService
from app.projects.registry import ProjectNotFoundError, ProjectRegistry, ProjectRuntime
from app.prometheus import PrometheusClient


def get_registry(request: Request) -> ProjectRegistry:
    return request.app.state.projects


async def get_runtime(slug: str, request: Request) -> ProjectRuntime:
    try:
        return await get_registry(request).runtime(slug)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


Runtime = Annotated[ProjectRuntime, Depends(get_runtime)]
Registry = Annotated[ProjectRegistry, Depends(get_registry)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_prometheus(runtime: Runtime) -> PrometheusClient:
    return runtime.prometheus


def get_dashboard_service(runtime: Runtime) -> DashboardService:
    return runtime.dashboard


def get_catalog_store(runtime: Runtime) -> CatalogStore:
    return runtime.catalog_store


def get_catalog_builder(runtime: Runtime) -> CatalogBuilder:
    return runtime.catalog_builder


def get_knowledge(runtime: Runtime) -> KnowledgeService:
    return runtime.knowledge


async def get_dashboard_id(did: str, runtime: Runtime) -> str:
    """Validates the ``{did}`` path segment against the project's dashboards."""
    from app.dashboard.service import DashboardNotFoundError

    try:
        await runtime.dashboard.get(did)
    except DashboardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return did


DashboardId = Annotated[str, Depends(get_dashboard_id)]
Prometheus = Annotated[PrometheusClient, Depends(get_prometheus)]
Dashboards = Annotated[DashboardService, Depends(get_dashboard_service)]
Catalog = Annotated[CatalogStore, Depends(get_catalog_store)]
CatalogBuild = Annotated[CatalogBuilder, Depends(get_catalog_builder)]
Knowledge = Annotated[KnowledgeService, Depends(get_knowledge)]
