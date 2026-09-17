import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.prometheus import PrometheusClient

FIXTURES = Path(__file__).parent / "fixtures" / "prometheus"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
def fixture() -> Any:
    return load_fixture


def json_response(body: dict[str, Any], status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=body)


P = "/api/projects/default"


def mock_prometheus(client: TestClient, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    """Route the default project's Prometheus client through an httpx.MockTransport."""
    prometheus = PrometheusClient("http://prom.test:9090", transport=httpx.MockTransport(handler))
    runtime = client.app.state.projects._runtimes["default"]  # type: ignore[attr-defined]
    runtime.prometheus = prometheus
    runtime.catalog_builder._prometheus = prometheus


def canned(response: httpx.Response | Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_: httpx.Request) -> httpx.Response:
        if isinstance(response, Exception):
            raise response
        return response

    return handler


TIMESERIES_SPEC: dict[str, Any] = {
    "type": "timeseries",
    "title": "CPU idle",
    "queries": [
        {
            "refId": "A",
            "expr": "rate(node_cpu_seconds_total{mode='idle'}[5m])",
            "legend": "cpu {{cpu}}",
        }
    ],
    "unit": "percentunit",
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom.test:9090")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CATALOG_AUTOSTART", "false")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()
