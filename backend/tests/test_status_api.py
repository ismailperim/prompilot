from typing import Any

import httpx
from fastapi.testclient import TestClient

from tests.conftest import P, canned, json_response, mock_prometheus


def test_instance_status(client: TestClient) -> None:
    body = client.get("/api/status").json()
    assert body["llm"] == {"enabled": False, "model": None}
    assert body["projects"] == 1


def test_project_status_reports_reachable_prometheus(client: TestClient, fixture: Any) -> None:
    mock_prometheus(client, canned(json_response(fixture("buildinfo"))))
    body = client.get(f"{P}/status").json()
    assert body["project"]["slug"] == "default"
    assert body["prometheus"] == {
        "url": "http://prom.test:9090",
        "reachable": True,
        "version": fixture("buildinfo")["data"]["version"],
        "error": None,
    }


def test_project_status_reports_unreachable_prometheus(client: TestClient) -> None:
    mock_prometheus(client, canned(httpx.ConnectError("refused")))
    body = client.get(f"{P}/status").json()
    assert body["prometheus"]["reachable"] is False
    assert "cannot reach Prometheus" in body["prometheus"]["error"]


def test_project_status_reports_auth_problem(client: TestClient) -> None:
    mock_prometheus(client, canned(httpx.Response(401)))
    body = client.get(f"{P}/status").json()
    assert "PROMETHEUS_USERNAME" in body["prometheus"]["error"]


def test_unknown_project_is_404(client: TestClient) -> None:
    assert client.get("/api/projects/nope/status").status_code == 404
    assert client.get("/api/projects/nope/dashboard").status_code == 404
