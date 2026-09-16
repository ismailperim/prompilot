import pytest

from app.catalog.categorize import CATEGORIES, categorize, exporter_prefix


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("node_cpu_seconds_total", "cpu"),
        ("node_load1", "cpu"),
        ("node_memory_MemAvailable_bytes", "memory"),
        ("node_network_receive_bytes_total", "network"),
        ("node_disk_io_time_seconds_total", "disk"),
        ("node_filesystem_avail_bytes", "filesystem"),
        ("kube_pod_status_phase", "kubernetes"),
        ("apiserver_request_total", "kubernetes"),
        ("container_cpu_usage_seconds_total", "container"),
        ("container_memory_working_set_bytes", "container"),
        ("http_requests_total", "http"),
        ("nginx_connections_active", "http"),
        ("myapp_http_request_duration_seconds_bucket", "http"),
        ("pg_stat_database_xact_commit", "database"),
        ("redis_connected_clients", "database"),
        ("kafka_consumer_lag", "messaging"),
        ("go_goroutines", "go_runtime"),
        ("go_memstats_alloc_bytes", "go_runtime"),
        ("jvm_memory_used_bytes", "jvm"),
        ("process_resident_memory_bytes", "process"),
        ("process_cpu_seconds_total", "process"),
        ("DCGM_FI_DEV_GPU_UTIL", "gpu"),
        ("prometheus_tsdb_head_series", "prometheus"),
        ("scrape_duration_seconds", "prometheus"),
        ("up", "prometheus"),
        ("myapp_orders_processed_total", "app"),
        ("weird", "other"),
    ],
)
def test_categorize(name: str, expected: str) -> None:
    assert categorize(name) == expected


def test_every_result_is_a_known_category() -> None:
    for name in ["node_cpu_seconds_total", "x", "a_b", "go_x", "kube_x"]:
        assert categorize(name) in CATEGORIES


def test_exporter_prefix() -> None:
    assert exporter_prefix("node_cpu_seconds_total") == "node"
    assert exporter_prefix("DCGM_FI_DEV_GPU_UTIL") == "dcgm"
    assert exporter_prefix("up") is None
