"""Rule-based metric categorisation. Deterministic, instant, no LLM required.

Rules are checked in order; the first match wins. Contributors: add rules for
your exporter here, together with a case in ``tests/test_categorize.py``.
"""

from __future__ import annotations

import re
from typing import Final

CATEGORIES: Final[tuple[str, ...]] = (
    "cpu",
    "memory",
    "network",
    "disk",
    "filesystem",
    "kubernetes",
    "container",
    "http",
    "database",
    "messaging",
    "go_runtime",
    "process",
    "jvm",
    "gpu",
    "prometheus",
    "app",
    "other",
)

# (pattern, category). Patterns are matched with re.search against the metric name.
_RULES: Final[list[tuple[re.Pattern[str], str]]] = [
    (re.compile(p, re.IGNORECASE), c)
    for p, c in [
        # Runtimes first: they are unambiguous and would otherwise be caught by broad rules.
        (r"^go_", "go_runtime"),
        (r"^(jvm_|java_lang_)", "jvm"),
        (r"^process_", "process"),
        (r"^(prometheus_|promhttp_|scrape_|up$|alertmanager_)", "prometheus"),
        # Hardware / accelerators
        (r"^(DCGM_|nvidia_|gpu_|amd_gpu_|rocm_)", "gpu"),
        # Kubernetes / containers
        (
            r"^(kube_|kubernetes_|kubelet_|apiserver_|etcd_|coredns_|kubeproxy_|scheduler_|controller_)",
            "kubernetes",
        ),
        (r"^(container_|cadvisor_|docker_|containerd_|machine_)", "container"),
        # Web servers / proxies, before the resource rules (which would grab "_connections_")
        (r"^(nginx_|apache_|haproxy_|traefik_|envoy_|caddy_|istio_|grpc_)", "http"),
        # Datastores & queues
        (
            r"^(pg_|postgres|postgresql_|mysql_|mariadb_|mongodb_|redis_|memcached_|elasticsearch_|opensearch_|cassandra_|clickhouse_|influxdb_|cockroach|tidb_|sql_)",
            "database",
        ),
        (r"^(kafka_|rabbitmq_|nats_|pulsar_|activemq_|mqtt_|amqp_|celery_|sqs_)", "messaging"),
        # Node / host resources
        (
            r"(^node_cpu_|^cpu_|_cpu_|load1$|load5$|load15$|^node_pressure_cpu|^node_schedstat|^node_context_switches|^node_intr)",
            "cpu",
        ),
        (
            r"(^node_memory_|^node_vmstat_|_memory_|_mem_|_rss|_heap_|swap|^node_pressure_memory)",
            "memory",
        ),
        (
            r"(^node_network_|^node_netstat_|^node_sockstat_|^node_nf_conntrack|_network_|_net_|_tcp_|_udp_|_socket|_conn(ections)?_|bandwidth|receive_|transmit_)",
            "network",
        ),
        (
            r"(^node_disk_|_disk_|_io_|_iops|^node_pressure_io|block_device|_read_bytes|_write_bytes|_writes_|_reads_)",
            "disk",
        ),
        (r"(^node_filesystem_|_filesystem_|_fs_|_files_|_inodes|_volume_|_mount)", "filesystem"),
        # Traffic
        (
            r"(^http_|_http_|^nginx_|^apache_|^haproxy_|^traefik_|^envoy_|^caddy_|^istio_|_requests?_|_request_duration|_response_|_grpc_|^grpc_)",
            "http",
        ),
    ]
]

_EXPORTER_PREFIX = re.compile(r"^([A-Za-z]+)_")


def categorize(name: str) -> str:
    for pattern, category in _RULES:
        if pattern.search(name):
            return category
    # Anything with a recognisable exporter/app prefix but no resource match is app-level.
    return "app" if "_" in name else "other"


def exporter_prefix(name: str) -> str | None:
    """``node_cpu_seconds_total`` → ``node``. Used to group metrics by source."""
    match = _EXPORTER_PREFIX.match(name)
    return match.group(1).lower() if match else None
