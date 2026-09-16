from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.prometheus import (
    PrometheusAuthError,
    PrometheusClient,
    PrometheusError,
    PrometheusQueryError,
    PrometheusUnavailableError,
    compute_step,
)
from tests.conftest import json_response

BASE = "http://prom.test:9090"


class Recorder:
    """MockTransport handler that records the request and returns a canned response."""

    def __init__(self, response: httpx.Response | Exception) -> None:
        self.response = response
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


def make_client(
    response: httpx.Response | Exception, **kwargs: Any
) -> tuple[PrometheusClient, Recorder]:
    recorder = Recorder(response)
    client = PrometheusClient(BASE, transport=httpx.MockTransport(recorder), **kwargs)
    return client, recorder


class TestRequests:
    async def test_query_sends_expr_and_optional_time(self, fixture: Any) -> None:
        client, rec = make_client(json_response(fixture("scalar")))
        result = await client.query("scalar(count(up))", time=datetime(2024, 1, 1, tzinfo=UTC))

        assert rec.last.url.path == "/api/v1/query"
        assert rec.last.url.params["query"] == "scalar(count(up))"
        assert rec.last.url.params["time"] == "1704067200.000"
        assert result.result_type == "scalar"
        assert rec.last.headers["user-agent"] == "prompilot"

    async def test_query_range_derives_step_from_max_data_points(self, fixture: Any) -> None:
        client, rec = make_client(json_response(fixture("matrix")))
        end = datetime(2024, 1, 1, 12, tzinfo=UTC)
        start = end - timedelta(hours=6)
        await client.query_range("up", start=start, end=end, max_data_points=100)

        params = rec.last.url.params
        assert rec.last.url.path == "/api/v1/query_range"
        assert params["start"] == "1704088800.000"
        assert params["end"] == "1704110400.000"
        # 6h / 100 = 216s → next nice step is 300s
        assert params["step"] == "300"

    async def test_query_range_honours_explicit_step(self, fixture: Any) -> None:
        client, rec = make_client(json_response(fixture("matrix")))
        end = datetime(2024, 1, 1, tzinfo=UTC)
        await client.query_range(
            "up", start=end - timedelta(hours=1), end=end, step=timedelta(seconds=7)
        )
        assert rec.last.url.params["step"] == "7"

    async def test_warnings_are_surfaced(self, fixture: Any) -> None:
        client, _ = make_client(json_response(fixture("matrix_gaps")))
        end = datetime(2024, 1, 1, tzinfo=UTC)
        result = await client.query_range("up", start=end - timedelta(hours=1), end=end)
        assert result.warnings == ["PromQL info: metric might not be a counter"]

    async def test_label_values_defaults_to_metric_names(self, fixture: Any) -> None:
        client, rec = make_client(json_response(fixture("label_names")))
        names = await client.label_values()
        assert rec.last.url.path == "/api/v1/label/__name__/values"
        assert "up" in names or len(names) == 12

    async def test_label_values_with_matchers(self, fixture: Any) -> None:
        client, rec = make_client(json_response(fixture("label_names")))
        await client.label_values("job", match=["up", "node_cpu_seconds_total"])
        assert rec.last.url.path == "/api/v1/label/job/values"
        assert rec.last.url.params.get_list("match[]") == ["up", "node_cpu_seconds_total"]

    async def test_series(self, fixture: Any) -> None:
        client, rec = make_client(json_response(fixture("series")))
        rows = await client.series(["up"], limit=5)
        assert rec.last.url.params.get_list("match[]") == ["up"]
        assert rec.last.url.params["limit"] == "5"
        assert rows and rows[0]["__name__"] == "up"

    async def test_series_requires_a_selector(self) -> None:
        client, _ = make_client(json_response({"status": "success", "data": []}))
        with pytest.raises(ValueError):
            await client.series([])

    async def test_metadata(self, fixture: Any) -> None:
        client, rec = make_client(json_response(fixture("metadata")))
        meta = await client.metadata()
        assert rec.last.url.params["limit_per_metric"] == "1"
        assert meta["node_filesystem_size_bytes"][0].type == "gauge"
        assert meta["node_cpu_seconds_total"][0].type == "counter"
        assert "CPU" in meta["node_cpu_seconds_total"][0].help

    async def test_build_info(self, fixture: Any) -> None:
        client, _ = make_client(json_response(fixture("buildinfo")))
        info = await client.build_info()
        assert info["version"].startswith("3.")


class TestAuth:
    async def test_basic_auth_header_when_configured(self, fixture: Any) -> None:
        client, rec = make_client(
            json_response(fixture("buildinfo")), username="alice", password="s3cret"
        )
        await client.build_info()
        assert rec.last.headers["authorization"] == "Basic YWxpY2U6czNjcmV0"

    async def test_no_auth_header_by_default(self, fixture: Any) -> None:
        client, rec = make_client(json_response(fixture("buildinfo")))
        await client.build_info()
        assert "authorization" not in rec.last.headers

    async def test_401_maps_to_auth_error_with_hint(self) -> None:
        client, _ = make_client(httpx.Response(401, text="Unauthorized"))
        with pytest.raises(PrometheusAuthError, match="PROMETHEUS_USERNAME"):
            await client.build_info()


class TestErrors:
    async def test_bad_promql_maps_to_query_error(self, fixture: Any) -> None:
        client, _ = make_client(json_response(fixture("error_parse"), status_code=400))
        with pytest.raises(PrometheusQueryError) as exc_info:
            await client.query("rate(up")
        assert exc_info.value.error_type == "bad_data"
        assert "parse error" in str(exc_info.value)

    async def test_prometheus_side_failure_is_unavailable(self) -> None:
        body = {"status": "error", "errorType": "execution", "error": "query timed out"}
        client, _ = make_client(json_response(body, status_code=503))
        with pytest.raises(PrometheusUnavailableError):
            await client.query("up")

    async def test_5xx_without_json_is_unavailable(self) -> None:
        client, _ = make_client(httpx.Response(502, text="bad gateway"))
        with pytest.raises(PrometheusUnavailableError, match="502"):
            await client.build_info()

    async def test_non_prometheus_endpoint_gives_helpful_error(self) -> None:
        client, _ = make_client(httpx.Response(200, text="<html>Grafana</html>"))
        with pytest.raises(PrometheusError, match="pointing at a Prometheus server"):
            await client.build_info()

    async def test_connection_error_is_unavailable(self) -> None:
        client, _ = make_client(httpx.ConnectError("connection refused"))
        with pytest.raises(PrometheusUnavailableError, match="cannot reach Prometheus"):
            await client.build_info()

    async def test_timeout_is_unavailable(self) -> None:
        client, _ = make_client(httpx.ReadTimeout("slow"), timeout=timedelta(seconds=5))
        with pytest.raises(PrometheusUnavailableError, match="5s"):
            await client.build_info()


class TestComputeStep:
    END = datetime(2024, 1, 1, tzinfo=UTC)

    @pytest.mark.parametrize(
        ("span", "max_points", "expected_seconds"),
        [
            (timedelta(hours=1), 1000, 15),  # 3.6s raw → floor at min_step 15s
            (timedelta(hours=6), 100, 300),  # 216s → 300s
            (timedelta(days=1), 1000, 120),  # 86.4s → 120s
            (timedelta(days=7), 1000, 900),  # 604.8s → 900s
            (timedelta(days=30), 1000, 3600),  # 2592s → 1h
            (timedelta(days=365), 100, 345600),  # 315360s → rounded up to whole days (4d)
        ],
    )
    def test_nice_steps(self, span: timedelta, max_points: int, expected_seconds: int) -> None:
        step = compute_step(self.END - span, self.END, max_points)
        assert step == timedelta(seconds=expected_seconds)

    def test_custom_min_step(self) -> None:
        step = compute_step(
            self.END - timedelta(minutes=5), self.END, 1000, min_step=timedelta(seconds=1)
        )
        assert step == timedelta(seconds=1)

    def test_rejects_inverted_range(self) -> None:
        with pytest.raises(ValueError):
            compute_step(self.END, self.END - timedelta(hours=1), 1000)
