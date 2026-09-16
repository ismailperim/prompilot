from fastapi.testclient import TestClient

from app.catalog.models import MetricEntry


def _seed(client: TestClient) -> None:
    store = client.app.state.catalog_store  # type: ignore[attr-defined]
    store.replace_all_sync(
        [
            MetricEntry(
                name="node_cpu_seconds_total", type="counter", help="CPU time", category="cpu"
            ),
            MetricEntry(
                name="node_memory_MemFree_bytes",
                type="gauge",
                help="Free memory",
                category="memory",
            ),
        ]
    )
    store.set_meta_sync(state="ready", updated_at="2024-03-13T10:00:00+00:00")


def test_status_idle_by_default(client: TestClient) -> None:
    body = client.get("/api/catalog/status").json()
    assert body["state"] == "idle"
    assert body["metricCount"] == 0


def test_search_and_detail(client: TestClient) -> None:
    _seed(client)
    body = client.get("/api/catalog/search", params={"q": "cpu"}).json()
    assert body["query"] == "cpu"
    assert [h["name"] for h in body["hits"]] == ["node_cpu_seconds_total"]
    assert "score" in body["hits"][0]

    body = client.get("/api/catalog/search", params={"q": "node", "category": "memory"}).json()
    assert [h["name"] for h in body["hits"]] == ["node_memory_MemFree_bytes"]

    assert client.get("/api/catalog/search", params={"category": "nope"}).status_code == 422

    detail = client.get("/api/catalog/metrics/node_cpu_seconds_total")
    assert detail.status_code == 200
    assert detail.json()["type"] == "counter"
    assert client.get("/api/catalog/metrics/ghost").status_code == 404


def test_categories(client: TestClient) -> None:
    body = client.get("/api/catalog/categories").json()
    assert "cpu" in body and "other" in body


def test_rebuild_is_accepted_and_reported(client: TestClient) -> None:
    response = client.post("/api/catalog/rebuild")
    assert response.status_code == 202
    body = response.json()
    assert body["started"] is True
    assert body["status"]["state"] == "building"
