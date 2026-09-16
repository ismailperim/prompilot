from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.api.deps import get_prometheus
from app.prometheus import PrometheusClient
from tests.conftest import json_response


def _override(client: TestClient, response: httpx.Response | Exception) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        if isinstance(response, Exception):
            raise response
        return response

    prometheus = PrometheusClient("http://prom.test:9090", transport=httpx.MockTransport(handler))
    client.app.dependency_overrides[get_prometheus] = lambda: prometheus  # type: ignore[attr-defined]


def test_status_reports_reachable_prometheus(client: TestClient, fixture: Any) -> None:
    _override(client, json_response(fixture("buildinfo")))
    body = client.get("/api/status").json()
    assert body["prometheus"] == {
        "url": "http://prom.test:9090",
        "reachable": True,
        "version": fixture("buildinfo")["data"]["version"],
        "error": None,
    }
    assert body["llm"] == {"enabled": False, "model": None}


def test_status_reports_unreachable_prometheus(client: TestClient) -> None:
    _override(client, httpx.ConnectError("refused"))
    body = client.get("/api/status").json()
    assert body["prometheus"]["reachable"] is False
    assert "cannot reach Prometheus" in body["prometheus"]["error"]


def test_status_reports_auth_problem(client: TestClient) -> None:
    _override(client, httpx.Response(401))
    body = client.get("/api/status").json()
    assert body["prometheus"]["reachable"] is False
    assert "PROMETHEUS_USERNAME" in body["prometheus"]["error"]
