"""Round-trip against a real Prometheus. Skipped unless PROMPILOT_TEST_PROMETHEUS_URL is set.

docker compose up -d prometheus node-exporter
PROMPILOT_TEST_PROMETHEUS_URL=http://localhost:9090 uv run pytest -m integration
"""

import os
from datetime import UTC, datetime, timedelta

import pytest

from app.prometheus import PrometheusClient, PrometheusQueryError, to_frame

URL = os.environ.get("PROMPILOT_TEST_PROMETHEUS_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not URL, reason="PROMPILOT_TEST_PROMETHEUS_URL not set"),
]


async def test_live_round_trip() -> None:
    assert URL is not None
    async with PrometheusClient(URL) as client:
        info = await client.build_info()
        assert "version" in info

        names = await client.label_values()
        assert "up" in names

        end = datetime.now(tz=UTC)
        result = await client.query_range("up", start=end - timedelta(minutes=5), end=end)
        frame = to_frame(result, ref_id="A", legend="{{job}}")
        assert frame.fields[0].name == "time"
        assert len(frame.fields) >= 2

        with pytest.raises(PrometheusQueryError):
            await client.query("rate(up")
