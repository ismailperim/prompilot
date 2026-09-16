"""Execute a panel's queries against Prometheus and return frames."""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.config import parse_duration
from app.models import CamelModel
from app.panels.base import PanelSpec, Query
from app.prometheus import DataFrame, PrometheusClient, PrometheusError, to_frame


class PanelData(CamelModel):
    frames: list[DataFrame] = []
    error: str | None = None
    warnings: list[str] = []


async def _run_query(
    prometheus: PrometheusClient,
    query: Query,
    start: datetime,
    end: datetime,
    max_data_points: int,
) -> tuple[DataFrame, list[str]]:
    if query.instant:
        result = await prometheus.query(query.expr, time=end)
    else:
        result = await prometheus.query_range(
            query.expr, start=start, end=end, max_data_points=max_data_points
        )
    return to_frame(result, ref_id=query.ref_id, legend=query.legend), result.warnings


async def fetch_panel_data(
    prometheus: PrometheusClient,
    spec: PanelSpec,
    start: datetime,
    end: datetime,
    *,
    max_data_points: int,
) -> PanelData:
    """Run all queries of a panel concurrently. Errors are returned, never raised."""
    if spec.time_from:
        start = end - parse_duration(spec.time_from)
    try:
        results = await asyncio.gather(
            *(_run_query(prometheus, q, start, end, max_data_points) for q in spec.queries)
        )
    except PrometheusError as exc:
        return PanelData(error=str(exc))
    frames = [frame for frame, _ in results]
    warnings = [w for _, ws in results for w in ws]
    return PanelData(frames=frames, warnings=warnings)
