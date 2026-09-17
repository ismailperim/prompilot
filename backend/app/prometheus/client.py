"""Thin async client for the Prometheus HTTP API (v1).

Only the endpoints PromPilot needs are implemented. Every call goes through
``_get`` so timeouts, authentication and error mapping live in one place.
"""

from __future__ import annotations

import math
import ssl
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import certifi
import httpx

if TYPE_CHECKING:
    from app.config import Settings

USER_AGENT = "prompilot"

# Step candidates used by ``compute_step``; mirrors Grafana's "nice" intervals.
_NICE_STEPS_SECONDS = (
    1, 2, 5, 10, 15, 20, 30,
    60, 120, 300, 600, 900, 1200, 1800,
    3600, 7200, 10800, 21600, 43200, 86400,
)  # fmt: skip


class PrometheusError(Exception):
    """Base class for all Prometheus client errors."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PrometheusAuthError(PrometheusError):
    """Prometheus rejected our credentials (HTTP 401/403)."""


class PrometheusQueryError(PrometheusError):
    """The request was rejected as invalid (bad PromQL, bad parameters)."""

    def __init__(self, message: str, *, error_type: str, status_code: int | None = None) -> None:
        super().__init__(message, status_code=status_code)
        self.error_type = error_type


class PrometheusUnavailableError(PrometheusError):
    """Prometheus could not be reached or failed internally (network, timeout, 5xx)."""


@dataclass(slots=True)
class QueryResult:
    """Raw result of ``/api/v1/query`` or ``/api/v1/query_range``."""

    result_type: str  # matrix | vector | scalar | string
    result: Any
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class MetricMetadata:
    type: str  # counter | gauge | histogram | summary | unknown
    help: str
    unit: str


def compute_step(
    start: datetime,
    end: datetime,
    max_data_points: int,
    min_step: timedelta = timedelta(seconds=15),
) -> timedelta:
    """Pick a query step so a range yields at most ``max_data_points`` points.

    The raw ``range / max_data_points`` is rounded up to the next "nice"
    interval, and never goes below ``min_step`` (typically the scrape
    interval — asking for a finer step than that only duplicates samples).
    """
    span = (end - start).total_seconds()
    if span <= 0:
        raise ValueError("end must be after start")
    if max_data_points <= 0:
        raise ValueError("max_data_points must be positive")
    raw = max(span / max_data_points, min_step.total_seconds())
    for candidate in _NICE_STEPS_SECONDS:
        if candidate >= raw:
            return timedelta(seconds=candidate)
    return timedelta(seconds=math.ceil(raw / 86400) * 86400)


def _to_unix(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return f"{moment.timestamp():.3f}"


def _format_step(step: timedelta) -> str:
    seconds = step.total_seconds()
    return f"{int(seconds)}" if seconds.is_integer() else f"{seconds:.3f}"


def tls_context(verify: bool, ca_file: Path | None) -> ssl.SSLContext | bool:
    """What to hand httpx as ``verify``: off, the system store, or the system store plus a CA."""
    if not verify:
        return False
    if ca_file is None:
        return True
    context = ssl.create_default_context(cafile=certifi.where())
    context.load_verify_locations(cafile=str(ca_file))
    return context


class PrometheusClient:
    def __init__(
        self,
        base_url: str,
        *,
        username: str | None = None,
        password: str | None = None,
        timeout: timedelta = timedelta(seconds=30),
        tls_verify: bool = True,
        ca_file: Path | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        auth = httpx.BasicAuth(username, password or "") if username else None
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            auth=auth,
            timeout=timeout.total_seconds(),
            headers={"User-Agent": USER_AGENT},
            verify=tls_context(tls_verify, ca_file),
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> PrometheusClient:
        return cls(
            settings.prometheus_url,
            username=settings.prometheus_username,
            password=settings.prometheus_password,
            timeout=settings.prometheus_query_timeout,
            tls_verify=settings.prometheus_tls_verify,
            ca_file=settings.prometheus_ca_file,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> PrometheusClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # ---- endpoints -----------------------------------------------------

    async def query(self, expr: str, *, time: datetime | None = None) -> QueryResult:
        """Instant query (``/api/v1/query``)."""
        params: dict[str, Any] = {"query": expr}
        if time is not None:
            params["time"] = _to_unix(time)
        body = await self._get("/api/v1/query", params)
        return self._query_result(body)

    async def query_range(
        self,
        expr: str,
        *,
        start: datetime,
        end: datetime,
        step: timedelta | None = None,
        max_data_points: int = 1000,
    ) -> QueryResult:
        """Range query (``/api/v1/query_range``); step is derived when omitted."""
        if step is None:
            step = compute_step(start, end, max_data_points)
        params = {
            "query": expr,
            "start": _to_unix(start),
            "end": _to_unix(end),
            "step": _format_step(step),
        }
        body = await self._get("/api/v1/query_range", params)
        return self._query_result(body)

    async def label_values(
        self,
        label: str = "__name__",
        *,
        match: list[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[str]:
        """Values for a label (``/api/v1/label/<name>/values``); metric names by default."""
        params: dict[str, Any] = {}
        if match:
            params["match[]"] = match
        if start is not None:
            params["start"] = _to_unix(start)
        if end is not None:
            params["end"] = _to_unix(end)
        body = await self._get(f"/api/v1/label/{label}/values", params)
        return list(body["data"])

    async def labels(
        self,
        *,
        match: list[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """Label names (``/api/v1/labels``), optionally only for series matching selectors."""
        params: dict[str, Any] = {}
        if match:
            params["match[]"] = match
        if start is not None:
            params["start"] = _to_unix(start)
        if end is not None:
            params["end"] = _to_unix(end)
        if limit is not None:
            params["limit"] = limit
        body = await self._get("/api/v1/labels", params)
        return list(body["data"])

    async def series(
        self,
        match: list[str],
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        """Label sets matching selectors (``/api/v1/series``)."""
        if not match:
            raise ValueError("at least one selector is required")
        params: dict[str, Any] = {"match[]": match}
        if start is not None:
            params["start"] = _to_unix(start)
        if end is not None:
            params["end"] = _to_unix(end)
        if limit is not None:
            params["limit"] = limit
        body = await self._get("/api/v1/series", params)
        return list(body["data"])

    async def metadata(
        self, *, metric: str | None = None, limit_per_metric: int | None = 1
    ) -> dict[str, list[MetricMetadata]]:
        """Metric metadata (``/api/v1/metadata``): type, help text, unit."""
        params: dict[str, Any] = {}
        if metric is not None:
            params["metric"] = metric
        if limit_per_metric is not None:
            params["limit_per_metric"] = limit_per_metric
        body = await self._get("/api/v1/metadata", params)
        return {
            name: [
                MetricMetadata(
                    type=entry.get("type", "unknown"),
                    help=entry.get("help", ""),
                    unit=entry.get("unit", ""),
                )
                for entry in entries
            ]
            for name, entries in body["data"].items()
        }

    async def build_info(self) -> dict[str, str]:
        """Server version info (``/api/v1/status/buildinfo``); doubles as a reachability check."""
        body = await self._get("/api/v1/status/buildinfo", {})
        return dict(body["data"])

    # ---- internals -----------------------------------------------------

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._http.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise PrometheusUnavailableError(
                f"Prometheus did not respond within {self.timeout.total_seconds():g}s"
            ) from exc
        except httpx.HTTPError as exc:
            hint = ""
            if "CERTIFICATE_VERIFY_FAILED" in str(exc):
                hint = (
                    " (the certificate is not trusted: set PROMETHEUS_CA_FILE or turn off"
                    " certificate verification in the project settings)"
                )
            raise PrometheusUnavailableError(
                f"cannot reach Prometheus at {self.base_url}: {exc}{hint}"
            ) from exc
        return self._handle(response)

    def _handle(self, response: httpx.Response) -> dict[str, Any]:
        status = response.status_code
        if status in (401, 403):
            raise PrometheusAuthError(
                f"Prometheus rejected the request (HTTP {status}); "
                "check PROMETHEUS_USERNAME / PROMETHEUS_PASSWORD",
                status_code=status,
            )

        try:
            body = response.json()
        except ValueError:
            body = None

        if not isinstance(body, dict) or "status" not in body:
            if status >= 500:
                raise PrometheusUnavailableError(
                    f"Prometheus returned HTTP {status}", status_code=status
                )
            raise PrometheusError(
                f"unexpected response from {self.base_url} (HTTP {status}); "
                "is PROMETHEUS_URL pointing at a Prometheus server?",
                status_code=status,
            )

        if body["status"] == "error":
            error_type = str(body.get("errorType", "unknown"))
            message = str(body.get("error", "unknown error"))
            if status >= 500 or error_type in {"internal", "unavailable", "timeout"}:
                raise PrometheusUnavailableError(
                    f"Prometheus error ({error_type}): {message}", status_code=status
                )
            raise PrometheusQueryError(message, error_type=error_type, status_code=status)

        return body

    @staticmethod
    def _query_result(body: dict[str, Any]) -> QueryResult:
        data = body["data"]
        return QueryResult(
            result_type=data["resultType"],
            result=data["result"],
            warnings=list(body.get("warnings") or []),
        )
