"""PromPilot's own Prometheus metrics, served at /metrics.

A tool that builds dashboards should be observable itself: HTTP latency per
route, what the agent does and how long it takes, and catalog builds.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import Request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.responses import Response

HTTP_REQUESTS = Counter(
    "prompilot_http_requests_total",
    "HTTP requests handled",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "prompilot_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.02, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)

CHAT_REQUESTS = Counter(
    "prompilot_chat_requests_total",
    "Chat requests by outcome (answered, iteration_limit, error)",
    ["outcome"],
)
CHAT_DURATION = Histogram(
    "prompilot_chat_duration_seconds",
    "Wall time of a chat request from first model call to done",
    buckets=(1, 2, 5, 10, 20, 30, 60, 120, 300),
)
LLM_TURNS = Histogram(
    "prompilot_llm_turns_per_chat",
    "Model turns needed per chat request",
    buckets=(1, 2, 3, 4, 6, 8, 12),
)
LLM_TURN_DURATION = Histogram(
    "prompilot_llm_turn_duration_seconds",
    "Latency of one model turn (streaming, until the turn completes)",
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120),
)
TOOL_CALLS = Counter(
    "prompilot_tool_calls_total",
    "Agent tool calls by tool and result",
    ["tool", "ok"],
)
TOOL_DURATION = Histogram(
    "prompilot_tool_call_duration_seconds",
    "Latency of a tool call",
    ["tool"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)

CATALOG_BUILDS = Counter(
    "prompilot_catalog_builds_total", "Catalog builds by outcome", ["project", "outcome"]
)
CATALOG_BUILD_DURATION = Histogram(
    "prompilot_catalog_build_duration_seconds",
    "Duration of a catalog build",
    ["project"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)
CATALOG_METRICS = Gauge(
    "prompilot_catalog_metrics", "Metrics in the catalog after the last build", ["project"]
)
PROJECTS = Gauge("prompilot_projects", "Configured projects")


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return str(path)
    # Static files and unknown paths: keep the label space small.
    return "static" if not request.url.path.startswith("/api") else "unmatched"


async def http_metrics_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if request.url.path == "/metrics":
        return await call_next(request)
    started = time.perf_counter()
    status = "500"
    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        route = _route_template(request)
        HTTP_REQUESTS.labels(request.method, route, status).inc()
        HTTP_LATENCY.labels(request.method, route).observe(time.perf_counter() - started)


async def metrics_endpoint(_: Request) -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
