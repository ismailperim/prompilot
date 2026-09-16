from typing import Any

import httpx
from fastapi.testclient import TestClient

from tests.conftest import canned, json_response, mock_prometheus


def test_status_reports_reachable_prometheus(client: TestClient, fixture: Any) -> None:
    mock_prometheus(client, canned(json_response(fixture("buildinfo"))))
    body = client.get("/api/status").json()
    assert body["prometheus"] == {
        "url": "http://prom.test:9090",
        "reachable": True,
        "version": fixture("buildinfo")["data"]["version"],
        "error": None,
    }
    assert body["llm"] == {"enabled": False, "model": None}


def test_status_reports_unreachable_prometheus(client: TestClient) -> None:
    mock_prometheus(client, canned(httpx.ConnectError("refused")))
    body = client.get("/api/status").json()
    assert body["prometheus"]["reachable"] is False
    assert "cannot reach Prometheus" in body["prometheus"]["error"]


def test_status_reports_auth_problem(client: TestClient) -> None:
    mock_prometheus(client, canned(httpx.Response(401)))
    body = client.get("/api/status").json()
    assert body["prometheus"]["reachable"] is False
    assert "PROMETHEUS_USERNAME" in body["prometheus"]["error"]
