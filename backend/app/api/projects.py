"""Project CRUD and per-project status."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.api.deps import Registry, Runtime
from app.models import CamelModel
from app.projects.models import Project, ProjectCreate, ProjectUpdate
from app.projects.registry import ProjectExistsError, ProjectNotFoundError
from app.prometheus import PrometheusClient, PrometheusError

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ConnectionTest(CamelModel):
    prometheus_url: str
    prometheus_username: str | None = None
    prometheus_password: str | None = None


class ConnectionResult(CamelModel):
    ok: bool
    version: str | None = None
    error: str | None = None


class PrometheusStatus(CamelModel):
    url: str
    reachable: bool
    version: str | None = None
    error: str | None = None


class ProjectStatus(CamelModel):
    project: Project
    prometheus: PrometheusStatus


@router.get("", response_model=list[Project])
async def list_projects(registry: Registry) -> list[Project]:
    return await registry.list()


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, registry: Registry) -> Project:
    try:
        return await registry.create(body)
    except ProjectExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/test", response_model=ConnectionResult)
async def test_connection(body: ConnectionTest) -> ConnectionResult:
    """Try the credentials without saving anything."""
    client = PrometheusClient(
        body.prometheus_url,
        username=body.prometheus_username or None,
        password=body.prometheus_password or None,
    )
    try:
        info = await client.build_info()
        return ConnectionResult(ok=True, version=info.get("version"))
    except PrometheusError as exc:
        return ConnectionResult(ok=False, error=str(exc))
    finally:
        await client.aclose()


@router.get("/{slug}", response_model=Project)
async def get_project(slug: str, registry: Registry) -> Project:
    try:
        return await registry.get(slug)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{slug}", response_model=Project)
async def update_project(slug: str, body: ProjectUpdate, registry: Registry) -> Project:
    try:
        return await registry.update(slug, body)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(slug: str, registry: Registry) -> Response:
    try:
        await registry.delete(slug)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{slug}/status", response_model=ProjectStatus)
async def project_status(runtime: Runtime) -> ProjectStatus:
    """Is this project's Prometheus reachable?"""
    try:
        info = await runtime.prometheus.build_info()
        prom = PrometheusStatus(
            url=runtime.prometheus.base_url, reachable=True, version=info.get("version")
        )
    except PrometheusError as exc:
        prom = PrometheusStatus(url=runtime.prometheus.base_url, reachable=False, error=str(exc))
    return ProjectStatus(project=runtime.project, prometheus=prom)
