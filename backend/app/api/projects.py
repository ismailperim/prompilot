"""Project CRUD and per-project status."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.api.deps import AppSettings, Registry, Runtime
from app.config import Settings
from app.models import CamelModel
from app.projects.models import Project, ProjectCreate, ProjectUpdate, Source
from app.projects.registry import (
    ProjectExistsError,
    ProjectInvalidError,
    ProjectManagedError,
    ProjectNotFoundError,
    ProjectRegistry,
)
from app.prometheus import PrometheusClient, PrometheusError
from app.prometheus.grafana import list_prometheus_datasources

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ConnectionTest(CamelModel):
    source: Source = "prometheus"
    prometheus_url: str | None = None
    grafana_url: str | None = None
    grafana_datasource_uid: str | None = None
    prometheus_username: str | None = None
    prometheus_password: str | None = None
    tls_verify: bool | None = None
    # Editing a project: a blank password means "use the stored one".
    slug: str | None = None


class GrafanaLookup(CamelModel):
    grafana_url: str
    prometheus_username: str | None = None
    prometheus_password: str | None = None
    tls_verify: bool | None = None
    slug: str | None = None


class GrafanaDatasourceInfo(CamelModel):
    uid: str
    name: str
    is_default: bool


class GrafanaDatasourceList(CamelModel):
    ok: bool
    datasources: list[GrafanaDatasourceInfo] = []
    error: str | None = None


async def _password(
    given: str | None, username: str | None, slug: str | None, registry: ProjectRegistry
) -> str | None:
    if given or not (slug and username):
        return given or None
    try:
        return await registry.stored_password(slug)
    except ProjectNotFoundError:
        return None


def _tls(value: bool | None, settings: Settings) -> bool:
    return value if value is not None else settings.prometheus_tls_verify


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
async def test_connection(
    body: ConnectionTest, settings: AppSettings, registry: Registry
) -> ConnectionResult:
    """Try the credentials without saving anything."""
    via_grafana = body.source == "grafana"
    url = (body.grafana_url if via_grafana else body.prometheus_url) or ""
    if not url.strip() or (via_grafana and not (body.grafana_datasource_uid or "").strip()):
        missing = "a Grafana URL and datasource" if via_grafana else "a Prometheus URL"
        return ConnectionResult(ok=False, error=f"{missing} is required")
    username = body.prometheus_username or None
    uid = (body.grafana_datasource_uid or "").strip() if via_grafana else ""
    client = PrometheusClient(
        url.strip(),
        grafana_datasource_uid=uid or None,
        username=username,
        password=await _password(body.prometheus_password, username, body.slug, registry),
        tls_verify=_tls(body.tls_verify, settings),
        ca_file=settings.prometheus_ca_file,
    )
    try:
        info = await client.build_info()
        return ConnectionResult(ok=True, version=info.get("version"))
    except PrometheusError as exc:
        return ConnectionResult(ok=False, error=str(exc))
    finally:
        await client.aclose()


@router.post("/grafana/datasources", response_model=GrafanaDatasourceList)
async def grafana_datasources(
    body: GrafanaLookup, settings: AppSettings, registry: Registry
) -> GrafanaDatasourceList:
    """Prometheus datasources the given Grafana user can query, default first."""
    username = body.prometheus_username or None
    try:
        found = await list_prometheus_datasources(
            body.grafana_url.strip(),
            username=username,
            password=await _password(body.prometheus_password, username, body.slug, registry),
            timeout=settings.prometheus_query_timeout,
            tls_verify=_tls(body.tls_verify, settings),
            ca_file=settings.prometheus_ca_file,
        )
    except PrometheusError as exc:
        return GrafanaDatasourceList(ok=False, error=str(exc))
    return GrafanaDatasourceList(
        ok=True,
        datasources=[
            GrafanaDatasourceInfo(uid=d.uid, name=d.name, is_default=d.is_default) for d in found
        ],
    )


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
    except ProjectInvalidError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProjectManagedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(slug: str, registry: Registry) -> Response:
    try:
        await registry.delete(slug)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectManagedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{slug}/status", response_model=ProjectStatus)
async def project_status(runtime: Runtime) -> ProjectStatus:
    """Is this project's Prometheus reachable?"""
    try:
        info = await runtime.prometheus.build_info()
        prom = PrometheusStatus(
            url=runtime.prometheus.display_url, reachable=True, version=info.get("version")
        )
    except PrometheusError as exc:
        prom = PrometheusStatus(url=runtime.prometheus.display_url, reachable=False, error=str(exc))
    return ProjectStatus(project=runtime.project, prometheus=prom)
