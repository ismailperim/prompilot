"""The scenarios. Each is one user request against the demo stack (Prometheus +
node-exporter) with deterministic checks on what the agent did.

Keep requests the way people actually type them; the point is to measure the
whole path from a loose sentence to a panel that shows data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Expect:
    """Every non-empty field must hold for the case to pass."""

    # Tool names that must appear at least once / must not appear at all.
    tools: tuple[str, ...] = ()
    no_tools: tuple[str, ...] = ()
    # Panels emitted in this turn (emit_panel calls that succeeded).
    panels: int | None = None
    panels_min: int | None = None
    panel_type: str | None = None
    unit_in: tuple[str, ...] = ()
    # Regexes; each must match at least one query expression of the emitted panels.
    expr: tuple[str, ...] = ()
    # Regexes that must match no emitted expression.
    expr_not: tuple[str, ...] = ()
    # Every emitted panel's queries return data from Prometheus.
    data: bool = False
    # Regex the final answer must match (case-insensitive).
    answer: str | None = None
    # ISO 639-1 code the answer must be written in (heuristic, tr/de/en).
    lang: str | None = None
    # Ids of preloaded panels that must have been patched / removed.
    patched: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    # Upper bound on model turns; catches thrashing.
    max_iterations: int | None = None


@dataclass(frozen=True)
class Case:
    id: str
    message: str
    expect: Expect
    # Panels already on the dashboard when the request arrives (spec dicts).
    panels: tuple[dict[str, Any], ...] = ()
    # Prior conversation turns (role/content), for follow-up requests.
    history: tuple[dict[str, str], ...] = ()
    tags: tuple[str, ...] = field(default_factory=tuple)


def _panel(id: str, type: str, title: str, expr: str, unit: str = "short") -> dict[str, Any]:
    return {"id": id, "type": type, "title": title, "unit": unit, "queries": [{"expr": expr}]}


CPU_PANEL = _panel(
    "p-cpu",
    "timeseries",
    "CPU busy per core",
    '1 - rate(node_cpu_seconds_total{mode="idle"}[5m])',
    "percentunit",
)
MEM_PANEL = _panel(
    "p-mem",
    "timeseries",
    "Memory used",
    "node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes",
    "bytes",
)
UP_PANEL = _panel("p-up", "stat", "Targets up", "sum(up)")

TIMESERIES = Expect(tools=("emit_panel",), panels=1, panel_type="timeseries", data=True)

CASES: list[Case] = [
    # ---- host basics -----------------------------------------------------
    Case(
        "cpu-per-core",
        "Show CPU usage per core as a percentage",
        Expect(
            tools=("emit_panel",),
            panels=1,
            panel_type="timeseries",
            unit_in=("percent", "percentunit"),
            expr=(r"node_cpu_seconds_total", r"i?rate\(", r'mode="idle"'),
            data=True,
        ),
        tags=("cpu", "basic"),
    ),
    Case(
        "memory-available",
        "Memory available over time",
        Expect(
            tools=("emit_panel",),
            panels=1,
            panel_type="timeseries",
            unit_in=("bytes", "decbytes"),
            expr=(r"node_memory_MemAvailable_bytes",),
            data=True,
        ),
        tags=("memory", "basic"),
    ),
    Case(
        "memory-used-percent",
        "How much of the memory is in use right now, as a percentage?",
        Expect(
            tools=("emit_panel",),
            panels=1,
            unit_in=("percent", "percentunit"),
            expr=(r"node_memory_MemTotal_bytes", r"node_memory_MemAvailable_bytes"),
            data=True,
        ),
        tags=("memory",),
    ),
    Case(
        "root-disk-usage",
        "Root filesystem usage",
        Expect(
            tools=("emit_panel",),
            panels_min=1,
            unit_in=("percent", "percentunit", "bytes"),
            expr=(r"node_filesystem_(avail|free|size)_bytes",),
            data=True,
        ),
        tags=("disk",),
    ),
    Case(
        "network-per-interface",
        "Network throughput per interface, received and transmitted",
        Expect(
            tools=("emit_panel",),
            panels_min=1,
            unit_in=("Bps", "bps", "bytes", "decbytes"),
            expr=(
                r"node_network_receive_bytes_total",
                r"node_network_transmit_bytes_total",
                r"i?rate\(",
            ),
            data=True,
        ),
        tags=("network",),
    ),
    Case(
        "disk-io",
        "disk I/O per device, last 6 hours",
        Expect(
            tools=("emit_panel",),
            panels_min=1,
            expr=(r"node_disk_(read|written)_bytes_total", r"i?rate\("),
            data=True,
        ),
        tags=("disk",),
    ),
    Case(
        "load-average",
        "load average 1, 5 and 15 minutes on one chart",
        Expect(
            tools=("emit_panel",),
            panels=1,
            panel_type="timeseries",
            expr=(r"node_load1\b", r"node_load5\b", r"node_load15\b"),
            data=True,
        ),
        tags=("cpu",),
    ),
    Case(
        "uptime",
        "How long has the host been up?",
        Expect(
            tools=("emit_panel",),
            panels=1,
            unit_in=("s", "short", "none"),
            expr=(r"node_boot_time_seconds|node_time_seconds",),
            data=True,
        ),
        tags=("basic",),
    ),
    Case(
        "swap",
        "swap usage",
        Expect(tools=("emit_panel",), panels_min=1, expr=(r"node_memory_Swap",), data=True),
        tags=("memory",),
    ),
    Case(
        "context-switches",
        "context switches per second",
        Expect(
            tools=("emit_panel",),
            panels=1,
            expr=(r"node_context_switches_total", r"i?rate\("),
            data=True,
        ),
        tags=("cpu",),
    ),
    Case(
        "network-errors",
        "Are there any network errors or drops?",
        Expect(
            tools=("emit_panel",),
            panels_min=1,
            expr=(r"node_network_(receive|transmit)_(errs|drop)_total",),
            data=True,
        ),
        tags=("network",),
    ),
    Case(
        "tcp-established",
        "established TCP connections",
        Expect(tools=("emit_panel",), panels=1, expr=(r"node_netstat_Tcp_CurrEstab",), data=True),
        tags=("network",),
    ),
    Case(
        "top-filesystems",
        "top 5 filesystems by usage as a table",
        Expect(
            tools=("emit_panel",),
            panels=1,
            panel_type="table",
            expr=(r"node_filesystem_", r"topk\(\s*5|sort"),
            data=True,
        ),
        tags=("disk", "table"),
    ),
    # ---- prometheus itself ------------------------------------------------
    Case(
        "scrape-duration",
        "How long do Prometheus scrapes take?",
        Expect(
            tools=("emit_panel",),
            panels_min=1,
            unit_in=("s", "ms"),
            expr=(r"scrape_duration_seconds",),
            data=True,
        ),
        tags=("prometheus",),
    ),
    Case(
        "targets-table",
        "a table of all scrape targets and whether they are up",
        Expect(
            tools=("emit_panel",),
            panels=1,
            panel_type="table",
            expr=(r"\bup\b",),
            data=True,
        ),
        tags=("prometheus", "table"),
    ),
    Case(
        "head-series",
        "number of active time series in the TSDB",
        Expect(tools=("emit_panel",), panels=1, expr=(r"prometheus_tsdb_head_series",), data=True),
        tags=("prometheus",),
    ),
    Case(
        "http-p99",
        "p99 latency of Prometheus HTTP requests",
        Expect(
            tools=("emit_panel",),
            panels=1,
            unit_in=("s", "ms"),
            expr=(
                r"histogram_quantile\(\s*0\.99",
                r"prometheus_http_request_duration_seconds_bucket",
            ),
            data=True,
        ),
        tags=("prometheus", "histogram"),
    ),
    Case(
        "http-rate-by-handler",
        "request rate to Prometheus by handler",
        Expect(
            tools=("emit_panel",),
            panels=1,
            unit_in=("reqps", "rps", "ops", "short"),
            expr=(r"prometheus_http_requests_total", r"i?rate\(", r"by\s*\(\s*handler\s*\)"),
            data=True,
        ),
        tags=("prometheus",),
    ),
    Case(
        "goroutines",
        "goroutines per job",
        Expect(tools=("emit_panel",), panels=1, expr=(r"go_goroutines",), data=True),
        tags=("prometheus",),
    ),
    Case(
        "open-fds",
        "open file descriptors of the prometheus process",
        Expect(
            tools=("emit_panel",),
            panels=1,
            expr=(r"process_open_fds", r'job="prometheus"'),
            data=True,
        ),
        tags=("prometheus",),
    ),
    # ---- questions, not panels ---------------------------------------------
    Case(
        "question-targets",
        "Which jobs are being scraped? Just tell me, no chart.",
        Expect(no_tools=("emit_panel",), answer=r"node.*prometheus|prometheus.*node"),
        tags=("question",),
    ),
    Case(
        "missing-metric",
        "show kafka consumer lag per topic",
        Expect(no_tools=("emit_panel",), answer=r"no|not|couldn|can't|isn't|doesn't|unable|kafka"),
        tags=("question", "negative"),
    ),
    # ---- languages -----------------------------------------------------------
    Case(
        "turkish-cpu",
        "çekirdek başına işlemci kullanımını yüzde olarak göster",
        Expect(
            tools=("emit_panel",),
            panels=1,
            unit_in=("percent", "percentunit"),
            expr=(r"node_cpu_seconds_total",),
            data=True,
            lang="tr",
        ),
        tags=("cpu", "lang"),
    ),
    Case(
        "german-memory",
        "Zeig mir den freien Arbeitsspeicher über die Zeit",
        Expect(
            tools=("emit_panel",),
            panels=1,
            expr=(r"node_memory_MemAvailable_bytes",),
            data=True,
            lang="de",
        ),
        tags=("memory", "lang"),
    ),
    # ---- editing what is there ---------------------------------------------
    Case(
        "rename-panel",
        "rename the memory panel to “RAM”",
        Expect(tools=("patch_panel",), no_tools=("emit_panel", "remove_panel"), patched=("p-mem",)),
        panels=(CPU_PANEL, MEM_PANEL),
        tags=("edit",),
    ),
    Case(
        "change-type",
        "turn the targets panel into a table",
        Expect(patched=("p-up",), no_tools=("remove_panel",)),
        panels=(CPU_PANEL, UP_PANEL),
        tags=("edit",),
    ),
    Case(
        "remove-all",
        "remove all panels",
        Expect(
            tools=("remove_panel",), no_tools=("emit_panel",), removed=("p-cpu", "p-mem", "p-up")
        ),
        panels=(CPU_PANEL, MEM_PANEL, UP_PANEL),
        tags=("edit",),
    ),
    Case(
        "remove-one",
        "drop the CPU chart, keep the rest",
        Expect(removed=("p-cpu",), no_tools=("emit_panel",)),
        panels=(CPU_PANEL, MEM_PANEL, UP_PANEL),
        tags=("edit",),
    ),
    Case(
        "follow-up",
        "now the same for memory",
        Expect(
            tools=("emit_panel",),
            panels=1,
            expr=(r"node_memory_",),
            data=True,
        ),
        panels=(CPU_PANEL,),
        history=(
            {"role": "user", "content": "Show CPU busy per core"},
            {"role": "assistant", "content": "Added “CPU busy per core” as a time series."},
        ),
        tags=("edit", "context"),
    ),
    Case(
        "unit-sanity",
        "disk read throughput",
        Expect(
            tools=("emit_panel",),
            panels=1,
            unit_in=("Bps", "bps"),
            expr=(r"node_disk_read_bytes_total", r"i?rate\("),
            data=True,
        ),
        tags=("disk", "unit"),
    ),
]

BY_ID = {c.id: c for c in CASES}
