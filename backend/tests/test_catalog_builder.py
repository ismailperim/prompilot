import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from app.catalog.builder import CatalogBuilder
from app.catalog.store import CatalogStore
from app.prometheus import PrometheusClient
from tests.conftest import json_response, load_fixture

NAMES = ["node_cpu_seconds_total", "node_filesystem_size_bytes", "up", "myapp_http_requests_total"]


def fake_prometheus(calls: list[httpx.Request], *, fail: bool = False) -> PrometheusClient:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if fail:
            return httpx.Response(502, text="bad gateway")
        path = request.url.path
        if path == "/api/v1/label/__name__/values":
            return json_response({"status": "success", "data": NAMES})
        if path == "/api/v1/metadata":
            return json_response(load_fixture("metadata"))
        if path == "/api/v1/labels":
            metric = request.url.params.get_list("match[]")[0]
            labels = {"node_cpu_seconds_total": ["__name__", "cpu", "instance", "job", "mode"]}.get(
                metric, ["__name__", "instance", "job"]
            )
            return json_response({"status": "success", "data": labels})
        return json_response({"status": "error", "errorType": "bad_data", "error": "nope"}, 400)

    return PrometheusClient("http://prom.test:9090", transport=httpx.MockTransport(handler))


@pytest.fixture
def store(tmp_path: Path) -> CatalogStore:
    return CatalogStore(tmp_path / "catalog.sqlite")


async def test_build_discovers_categorises_and_samples_labels(store: CatalogStore) -> None:
    calls: list[httpx.Request] = []
    builder = CatalogBuilder(fake_prometheus(calls), store, label_sample_limit=2, concurrency=2)

    status = await builder.build()

    assert status.state == "ready"
    assert status.metric_count == 4
    assert status.updated_at is not None
    assert status.categories == {"cpu": 1, "filesystem": 1, "prometheus": 1, "http": 1}

    cpu = store.get_sync("node_cpu_seconds_total")
    assert cpu is not None
    assert cpu.type == "counter"
    assert "CPUs" in cpu.help
    assert cpu.exporter == "node"

    # Only the first two (sorted) metrics had their labels sampled.
    sampled = {n for n in store.names_sync() if store.get_sync(n).labels_sampled}  # type: ignore[union-attr]
    assert sampled == {"myapp_http_requests_total", "node_cpu_seconds_total"}
    assert store.get_sync("node_cpu_seconds_total").labels == ["cpu", "instance", "job", "mode"]  # type: ignore[union-attr]
    assert len([c for c in calls if c.url.path == "/api/v1/labels"]) == 2


async def test_build_failure_is_recorded_not_raised(store: CatalogStore) -> None:
    builder = CatalogBuilder(fake_prometheus([], fail=True), store)
    status = await builder.build()
    assert status.state == "error"
    assert status.error is not None and "502" in status.error
    assert status.metric_count == 0


async def wait_ready(builder: CatalogBuilder, timeout: float = 5.0) -> None:
    """Poll instead of sleeping a fixed time: CI runners are slow and uneven."""
    deadline = asyncio.get_running_loop().time() + timeout
    # "ready" is only ever written by a completed build, so waiting for it covers the
    # scheduler's own start-up delay as well as the build itself.
    while builder.building or (await builder.status()).state != "ready":
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("catalog build did not finish in time")
        await asyncio.sleep(0.02)


async def test_trigger_runs_in_background_and_dedupes(store: CatalogStore) -> None:
    builder = CatalogBuilder(fake_prometheus([]), store, label_sample_limit=0)
    assert builder.trigger() is True
    assert builder.trigger() is False  # already running
    assert builder.building
    await wait_ready(builder)
    assert not builder.building
    assert (await builder.status()).state == "ready"


async def test_ensure_labels_samples_on_demand(store: CatalogStore) -> None:
    calls: list[httpx.Request] = []
    builder = CatalogBuilder(fake_prometheus(calls), store, label_sample_limit=0)
    await builder.build()
    entry = store.get_sync("node_cpu_seconds_total")
    assert entry is not None and not entry.labels_sampled

    enriched = await builder.ensure_labels(entry)
    assert enriched.labels == ["cpu", "instance", "job", "mode"]
    assert enriched.labels_sampled
    assert store.get_sync("node_cpu_seconds_total").labels_sampled  # type: ignore[union-attr]

    # second call hits the store, not Prometheus
    before = len(calls)
    await builder.ensure_labels(enriched)
    assert len(calls) == before


async def test_scheduler_skips_fresh_catalog(store: CatalogStore) -> None:
    calls: list[httpx.Request] = []
    builder = CatalogBuilder(fake_prometheus(calls), store, rebuild_interval=timedelta(hours=1))
    await builder.build()
    n = len(calls)

    builder.start()
    await asyncio.sleep(0.05)
    assert len(calls) == n  # fresh → no rebuild
    await builder.stop()


async def test_scheduler_rebuilds_stale_catalog(store: CatalogStore) -> None:
    calls: list[httpx.Request] = []
    builder = CatalogBuilder(fake_prometheus(calls), store, rebuild_interval=timedelta(0))
    builder.start()
    await wait_ready(builder)
    assert (await builder.status()).state == "ready"
    assert any(c.url.path == "/api/v1/metadata" for c in calls)
    await builder.stop()
