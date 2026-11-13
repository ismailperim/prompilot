"""Find the Prometheus datasources a Grafana user can query.

Used when a project reaches Prometheus through Grafana's datasource proxy, so
people pick a datasource by name instead of looking up its UID.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import httpx

from app.prometheus.client import (
    USER_AGENT,
    PrometheusAuthError,
    PrometheusError,
    PrometheusUnavailableError,
    tls_context,
)

# Datasource types that speak the Prometheus HTTP API through the proxy.
# Mimir, Cortex and Thanos are configured as the plain "prometheus" type.
PROMETHEUS_TYPES = frozenset({"prometheus"})


@dataclass(slots=True, frozen=True)
class GrafanaDatasource:
    uid: str
    name: str
    is_default: bool


async def list_prometheus_datasources(
    grafana_url: str,
    *,
    username: str | None = None,
    password: str | None = None,
    timeout: timedelta = timedelta(seconds=30),
    tls_verify: bool = True,
    ca_file: Path | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[GrafanaDatasource]:
    """Prometheus-type datasources visible to the user (``GET /api/datasources``)."""
    base = grafana_url.rstrip("/")
    auth = httpx.BasicAuth(username, password or "") if username else None
    async with httpx.AsyncClient(
        base_url=base,
        auth=auth,
        timeout=timeout.total_seconds(),
        headers={"User-Agent": USER_AGENT},
        verify=tls_context(tls_verify, ca_file),
        transport=transport,
    ) as http:
        try:
            response = await http.get("/api/datasources")
        except httpx.HTTPError as exc:
            raise PrometheusUnavailableError(f"cannot reach Grafana at {base}: {exc}") from exc

    if response.status_code in (401, 403):
        raise PrometheusAuthError(
            f"Grafana rejected the request (HTTP {response.status_code}); "
            "check the username and password",
            status_code=response.status_code,
        )
    try:
        body = response.json()
    except ValueError:
        body = None
    if response.status_code != 200 or not isinstance(body, list):
        raise PrometheusError(
            f"unexpected response from {base}/api/datasources (HTTP {response.status_code}); "
            "is this the Grafana URL?",
            status_code=response.status_code,
        )
    found = [
        GrafanaDatasource(
            uid=str(item["uid"]),
            name=str(item.get("name") or item["uid"]),
            is_default=bool(item.get("isDefault")),
        )
        for item in body
        if isinstance(item, dict) and item.get("type") in PROMETHEUS_TYPES and item.get("uid")
    ]
    return sorted(found, key=lambda d: (not d.is_default, d.name.lower()))
