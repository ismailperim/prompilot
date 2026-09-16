import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures" / "prometheus"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
def fixture() -> Any:
    return load_fixture


def json_response(body: dict[str, Any], status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=body)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom.test:9090")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()
