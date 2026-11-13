"""Reaching Prometheus through a Grafana datasource proxy."""

from __future__ import annotations

import base64
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.prometheus import (
    PrometheusAuthError,
    PrometheusClient,
    PrometheusError,
    PrometheusQueryError,
    PrometheusUnavailableError,
)
from app.prometheus.grafana import list_prometheus_datasources
from tests.conftest import json_response

GRAFANA = "https://grafana.test"
PROXY = "/api/datasources/proxy/uid/prom-1"


def _grafana_client(handler: Any, uid: str = "prom-1") -> PrometheusClient:
    return PrometheusClient(
        GRAFANA + "/",
        grafana_datasource_uid=uid,
        username="viewer",
        password="pw",
        transport=httpx.MockTransport(handler),
    )


async def test_queries_go_through_the_datasource_proxy(fixture: Any) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(fixture("vector"))

    client = _grafana_client(handler)
    result = await client.query("up")
    assert result.result_type == "vector"
    request = seen[0]
    assert request.url.path == f"{PROXY}/api/v1/query"
    assert request.url.params["query"] == "up"
    expected = base64.b64encode(b"viewer:pw").decode()
    assert request.headers["authorization"] == f"Basic {expected}"
    assert client.display_url == f"{GRAFANA} (Grafana datasource prom-1)"
    await client.aclose()


async def test_uid_is_escaped_in_the_path() -> None:
    client = _grafana_client(lambda _: httpx.Response(200), uid="a/b c")
    assert client.base_url == f"{GRAFANA}/api/datasources/proxy/uid/a%2Fb%20c"
    await client.aclose()


@pytest.mark.parametrize(
    ("response", "error", "text"),
    [
        (
            httpx.Response(401, json={"message": "Invalid username or password"}),
            PrometheusAuthError,
            "Grafana rejected the request (HTTP 401: Invalid username or password)",
        ),
        (
            httpx.Response(404, json={"message": "Unable to find datasource"}),
            PrometheusError,
            "has no datasource with UID 'prom-1'",
        ),
        (
            httpx.Response(502, text="Bad Gateway"),
            PrometheusUnavailableError,
            "Grafana could not reach the datasource's Prometheus (HTTP 502)",
        ),
    ],
)
async def test_grafana_errors_are_explained(
    response: httpx.Response, error: type[Exception], text: str
) -> None:
    client = _grafana_client(lambda _: response)
    with pytest.raises(error, match=r".*") as info:
        await client.query("up")
    assert text in str(info.value)
    await client.aclose()


async def test_prometheus_errors_relayed_by_grafana_keep_their_meaning(fixture: Any) -> None:
    client = _grafana_client(lambda _: json_response(fixture("error_parse"), status_code=400))
    with pytest.raises(PrometheusQueryError):
        await client.query("up(")
    await client.aclose()


async def test_list_prometheus_datasources() -> None:
    body = [
        {"uid": "loki", "name": "Logs", "type": "loki"},
        {"uid": "b", "name": "beta", "type": "prometheus"},
        {"uid": "a", "name": "Alpha", "type": "prometheus"},
        {"uid": "d", "name": "Mimir", "type": "prometheus", "isDefault": True},
    ]
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=body)

    found = await list_prometheus_datasources(
        GRAFANA, username="u", password="p", transport=httpx.MockTransport(handler)
    )
    assert [d.uid for d in found] == ["d", "a", "b"]  # default first, then by name
    assert seen[0].url.path == "/api/datasources"


async def test_list_prometheus_datasources_errors() -> None:
    with pytest.raises(PrometheusAuthError):
        await list_prometheus_datasources(
            GRAFANA, transport=httpx.MockTransport(lambda _: httpx.Response(401))
        )
    with pytest.raises(PrometheusError, match="is this the Grafana URL"):
        await list_prometheus_datasources(
            GRAFANA, transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<html>"))
        )


# ---- projects API ------------------------------------------------------------


def test_create_grafana_project(client: TestClient) -> None:
    created = client.post(
        "/api/projects",
        json={
            "name": "Via Grafana",
            "source": "grafana",
            "grafanaUrl": "https://grafana.test/",
            "grafanaDatasourceUid": " prom-1 ",
            "prometheusUsername": "viewer",
            "prometheusPassword": "pw",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source"] == "grafana"
    assert body["grafanaUrl"] == "https://grafana.test"
    assert body["grafanaDatasourceUid"] == "prom-1"
    assert body["prometheusUrl"] == ""
    assert body["hasPassword"] is True

    runtime = client.app.state.projects._runtimes["via-grafana"]  # type: ignore[attr-defined]
    assert runtime.prometheus.base_url == "https://grafana.test/api/datasources/proxy/uid/prom-1"

    status = client.get("/api/projects/via-grafana/status").json()
    assert status["prometheus"]["url"] == "https://grafana.test (Grafana datasource prom-1)"


def test_grafana_project_needs_url_and_uid(client: TestClient) -> None:
    missing = client.post(
        "/api/projects",
        json={"name": "x", "source": "grafana", "grafanaUrl": "https://grafana.test"},
    )
    assert missing.status_code == 422
    assert client.post("/api/projects", json={"name": "x"}).status_code == 422


def test_switch_project_between_sources(client: TestClient) -> None:
    switched = client.patch(
        "/api/projects/default",
        json={"source": "grafana", "grafanaUrl": "https://g.test", "grafanaDatasourceUid": "u"},
    )
    assert switched.status_code == 200, switched.text
    runtime = client.app.state.projects._runtimes["default"]  # type: ignore[attr-defined]
    assert runtime.prometheus.via_grafana

    # Switching back keeps the Prometheus URL the project had.
    back = client.patch("/api/projects/default", json={"source": "prometheus"})
    assert back.json()["prometheusUrl"] == "http://prom.test:9090"
    runtime = client.app.state.projects._runtimes["default"]  # type: ignore[attr-defined]
    assert not runtime.prometheus.via_grafana

    created = client.post(
        "/api/projects",
        json={
            "name": "g",
            "source": "grafana",
            "grafanaUrl": "https://g",
            "grafanaDatasourceUid": "u",
        },
    )
    assert created.status_code == 201
    # A Grafana-only project cannot switch to Prometheus without a URL.
    assert client.patch("/api/projects/g", json={"source": "prometheus"}).status_code == 422


def test_connection_test_through_grafana(
    client: TestClient, fixture: Any, monkeypatch: Any
) -> None:
    from app.api import projects as projects_api

    calls: list[dict[str, Any]] = []

    class FakeClient(projects_api.PrometheusClient):
        def __init__(self, base_url: str, **kwargs: Any) -> None:
            calls.append({"base_url": base_url, **kwargs})
            super().__init__(
                base_url,
                grafana_datasource_uid=kwargs.get("grafana_datasource_uid"),
                transport=httpx.MockTransport(lambda _: json_response(fixture("buildinfo"))),
            )

    monkeypatch.setattr(projects_api, "PrometheusClient", FakeClient)

    client.post(
        "/api/projects",
        json={
            "name": "g",
            "source": "grafana",
            "grafanaUrl": "https://g.test",
            "grafanaDatasourceUid": "u",
            "prometheusUsername": "viewer",
            "prometheusPassword": "stored-pw",
        },
    )
    calls.clear()
    result = client.post(
        "/api/projects/test",
        json={
            "source": "grafana",
            "grafanaUrl": "https://g.test",
            "grafanaDatasourceUid": "u",
            "prometheusUsername": "viewer",
            "slug": "g",  # blank password → the stored one is used
        },
    ).json()
    assert result["ok"] is True
    assert calls[0]["grafana_datasource_uid"] == "u"
    assert calls[0]["password"] == "stored-pw"

    incomplete = client.post(
        "/api/projects/test", json={"source": "grafana", "grafanaUrl": "https://g.test"}
    ).json()
    assert incomplete["ok"] is False and "datasource" in incomplete["error"]


def test_grafana_datasource_lookup_endpoint(client: TestClient, monkeypatch: Any) -> None:
    from app.api import projects as projects_api
    from app.prometheus.grafana import GrafanaDatasource

    async def fake_list(url: str, **kwargs: Any) -> list[GrafanaDatasource]:
        if kwargs["password"] != "pw":
            raise PrometheusAuthError("Grafana rejected the request (HTTP 401)")
        return [GrafanaDatasource(uid="d", name="Mimir", is_default=True)]

    monkeypatch.setattr(projects_api, "list_prometheus_datasources", fake_list)
    ok = client.post(
        "/api/projects/grafana/datasources",
        json={
            "grafanaUrl": "https://g.test",
            "prometheusUsername": "u",
            "prometheusPassword": "pw",
        },
    ).json()
    assert ok == {
        "ok": True,
        "datasources": [{"uid": "d", "name": "Mimir", "isDefault": True}],
        "error": None,
    }
    denied = client.post(
        "/api/projects/grafana/datasources",
        json={"grafanaUrl": "https://g.test", "prometheusUsername": "u", "prometheusPassword": "x"},
    ).json()
    assert denied["ok"] is False and "401" in denied["error"]


@pytest.fixture
def grafana_env_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    monkeypatch.setenv("GRAFANA_URL", "https://grafana.test")
    monkeypatch.setenv("GRAFANA_DATASOURCE_UID", "prom-1")
    monkeypatch.setenv("GRAFANA_USERNAME", "viewer")
    monkeypatch.setenv("GRAFANA_PASSWORD", "pw")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CATALOG_AUTOSTART", "false")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()


def test_default_project_from_grafana_env(grafana_env_client: TestClient) -> None:
    project = grafana_env_client.get("/api/projects/default").json()
    assert project["source"] == "grafana"
    assert project["grafanaUrl"] == "https://grafana.test"
    assert project["grafanaDatasourceUid"] == "prom-1"
    assert project["prometheusUsername"] == "viewer"
    assert project["hasPassword"] is True


def test_source_columns_are_added_to_old_databases(tmp_path: Path) -> None:
    import sqlite3

    from app.projects.store import ProjectStore

    db = tmp_path / "prompilot.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE projects (
            slug TEXT PRIMARY KEY, name TEXT NOT NULL, prometheus_url TEXT NOT NULL,
            prometheus_username TEXT, prometheus_password TEXT,
            tls_verify INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        INSERT INTO projects VALUES ('old', 'Old', 'http://old:9090', NULL, NULL, 1,
            '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()
    record = ProjectStore(db).list_sync()[0]
    assert record.source == "prometheus"
    assert record.grafana_url is None
