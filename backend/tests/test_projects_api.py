from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from tests.conftest import TIMESERIES_SPEC, canned, json_response, mock_prometheus


def test_default_project_comes_from_env(client: TestClient) -> None:
    projects = client.get("/api/projects").json()
    assert [p["slug"] for p in projects] == ["default"]
    assert projects[0]["prometheusUrl"] == "http://prom.test:9090"
    assert projects[0]["hasPassword"] is False


def test_create_update_delete_project(client: TestClient, tmp_path: Path) -> None:
    created = client.post(
        "/api/projects",
        json={
            "name": "Staging cluster",
            "prometheusUrl": "http://staging:9090/",
            "prometheusUsername": "alice",
            "prometheusPassword": "s3cret",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["slug"] == "staging-cluster"
    assert body["prometheusUrl"] == "http://staging:9090"  # trailing slash dropped
    assert body["hasPassword"] is True
    assert "prometheusPassword" not in body

    # its own database file, its own empty dashboard
    assert (tmp_path / "data" / "projects" / "staging-cluster.sqlite").exists()
    assert client.get("/api/projects/staging-cluster/dashboards/overview").json()["panels"] == []

    # duplicate slug
    assert (
        client.post(
            "/api/projects", json={"name": "Staging Cluster", "prometheusUrl": "http://x:1"}
        ).status_code
        == 409
    )

    # invalid url
    bad = client.post("/api/projects", json={"name": "x", "prometheusUrl": "staging:9090"})
    assert bad.status_code == 422

    updated = client.patch(
        "/api/projects/staging-cluster", json={"name": "Staging", "clearPassword": True}
    )
    assert updated.json()["name"] == "Staging"
    assert updated.json()["hasPassword"] is False

    assert client.delete("/api/projects/staging-cluster").status_code == 204
    assert client.get("/api/projects/staging-cluster").status_code == 404
    assert not (tmp_path / "data" / "projects" / "staging-cluster.sqlite").exists()
    assert client.delete("/api/projects/staging-cluster").status_code == 404


def test_projects_are_isolated(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "Other", "prometheusUrl": "http://other:9090"})
    client.post("/api/projects/default/dashboards/overview/panels", json={"spec": TIMESERIES_SPEC})
    assert len(client.get("/api/projects/default/dashboards/overview").json()["panels"]) == 1
    assert client.get("/api/projects/other/dashboards/overview").json()["panels"] == []
    assert client.get("/api/projects/other/catalog/status").json()["metricCount"] == 0


def test_connection_test(client: TestClient, fixture: Any, monkeypatch: Any) -> None:
    # Patch the client class used by the endpoint to avoid real network access.
    from app.api import projects as projects_api

    class FakeClient(projects_api.PrometheusClient):
        def __init__(self, base_url: str, **kwargs: Any) -> None:
            ok = "good" in base_url
            body = json_response(fixture("buildinfo")) if ok else httpx.Response(401)
            super().__init__(base_url, transport=httpx.MockTransport(canned(body)))

    monkeypatch.setattr(projects_api, "PrometheusClient", FakeClient)
    good = client.post("/api/projects/test", json={"prometheusUrl": "http://good:9090"}).json()
    assert good["ok"] is True and good["version"]
    bad = client.post("/api/projects/test", json={"prometheusUrl": "http://bad:9090"}).json()
    assert bad["ok"] is False and "PROMETHEUS_USERNAME" in bad["error"]


def test_project_status_after_swap(client: TestClient, fixture: Any) -> None:
    mock_prometheus(client, canned(json_response(fixture("buildinfo"))))
    assert client.get("/api/projects/default/status").json()["prometheus"]["reachable"] is True


def test_tls_verify_is_per_project(client: TestClient, monkeypatch: Any) -> None:
    assert client.get("/api/projects").json()[0]["tlsVerify"] is True

    created = client.post(
        "/api/projects",
        json={"name": "Self signed", "prometheusUrl": "https://prom.internal", "tlsVerify": False},
    )
    assert created.status_code == 201 and created.json()["tlsVerify"] is False
    runtime = client.app.state.projects._runtimes["self-signed"]  # type: ignore[attr-defined]
    assert runtime.prometheus._http._transport._pool._ssl_context.verify_mode == 0  # CERT_NONE

    updated = client.patch("/api/projects/self-signed", json={"tlsVerify": True})
    assert updated.json()["tlsVerify"] is True
    runtime = client.app.state.projects._runtimes["self-signed"]  # type: ignore[attr-defined]
    assert runtime.prometheus._http._transport._pool._ssl_context.verify_mode == 2  # CERT_REQUIRED


def test_tls_verify_column_is_added_to_old_databases(tmp_path: Path) -> None:
    import sqlite3

    from app.projects.store import ProjectStore

    db = tmp_path / "prompilot.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE projects (
            slug TEXT PRIMARY KEY, name TEXT NOT NULL, prometheus_url TEXT NOT NULL,
            prometheus_username TEXT, prometheus_password TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        INSERT INTO projects VALUES ('old', 'Old', 'http://old:9090', NULL, NULL,
            '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()
    records = ProjectStore(db).list_sync()
    assert records[0].tls_verify is True
