from pathlib import Path

import pytest

from app.catalog.models import MetricEntry
from app.catalog.store import CatalogStore, fts_query, name_tokens

ENTRIES = [
    MetricEntry(
        name="node_cpu_seconds_total",
        type="counter",
        help="Seconds the CPUs spent in each mode.",
        category="cpu",
        exporter="node",
        labels=["cpu", "instance", "job", "mode"],
        labels_sampled=True,
    ),
    MetricEntry(
        name="node_memory_MemAvailable_bytes",
        type="gauge",
        help="Memory information field MemAvailable_bytes.",
        category="memory",
        exporter="node",
    ),
    MetricEntry(
        name="container_cpu_usage_seconds_total",
        type="counter",
        help="Cumulative cpu time consumed",
        category="container",
        exporter="container",
        labels=["pod", "namespace", "container"],
        labels_sampled=True,
    ),
    MetricEntry(name="up", type="gauge", help="", category="prometheus"),
]


@pytest.fixture
def store(tmp_path: Path) -> CatalogStore:
    s = CatalogStore(tmp_path / "catalog.sqlite")
    s.replace_all_sync(ENTRIES)
    return s


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("cpu", '"cpu"*'),
        ("cpu usage", '"cpu"* AND "usage"*'),
        ("node_cpu", '"node"* AND "cpu"*'),
        ("  CPU!  ", '"cpu"*'),
        ("", None),
        ("***", None),
    ],
)
def test_fts_query(text: str, expected: str | None) -> None:
    assert fts_query(text) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("node_memory_MemAvailable_bytes", "node memory mem available bytes"),
        ("node_cpu_seconds_total", "node cpu seconds total"),
        ("DCGM_FI_DEV_GPU_UTIL", "dcgm fi dev gpu util"),
        ("http_requestsTotal", "http requests total"),
        ("up", "up"),
    ],
)
def test_name_tokens(name: str, expected: str) -> None:
    assert name_tokens(name) == expected


def test_search_splits_camel_case_names(store: CatalogStore) -> None:
    assert [h.name for h in store.search_sync("memory available")] == [
        "node_memory_MemAvailable_bytes"
    ]


def test_search_by_name_token(store: CatalogStore) -> None:
    names = [h.name for h in store.search_sync("cpu")]
    assert set(names) == {"node_cpu_seconds_total", "container_cpu_usage_seconds_total"}


def test_search_falls_back_to_any_word_when_all_words_fail(store: CatalogStore) -> None:
    names = [h.name for h in store.search_sync("cpu utilization")]
    assert set(names) == {"node_cpu_seconds_total", "container_cpu_usage_seconds_total"}
    # ...but a full match still wins when it exists
    assert [h.name for h in store.search_sync("cpu usage")] == ["container_cpu_usage_seconds_total"]
    assert store.search_sync("zzz qqq") == []


def test_search_prefix_matching(store: CatalogStore) -> None:
    assert [h.name for h in store.search_sync("mem")] == ["node_memory_MemAvailable_bytes"]


def test_search_matches_help_text_and_labels(store: CatalogStore) -> None:
    assert [h.name for h in store.search_sync("cumulative")] == [
        "container_cpu_usage_seconds_total"
    ]
    assert [h.name for h in store.search_sync("namespace")] == ["container_cpu_usage_seconds_total"]


def test_search_ranks_name_matches_first(store: CatalogStore) -> None:
    # "cpu" appears in both names; the container one also has it in the help → higher score.
    hits = store.search_sync("cpu")
    assert hits[0].score >= hits[1].score


def test_search_with_category_filter(store: CatalogStore) -> None:
    assert [h.name for h in store.search_sync("cpu", category="container")] == [
        "container_cpu_usage_seconds_total"
    ]
    assert store.search_sync("cpu", category="memory") == []


def test_empty_query_lists_metrics(store: CatalogStore) -> None:
    hits = store.search_sync("", limit=2)
    assert [h.name for h in hits] == ["container_cpu_usage_seconds_total", "node_cpu_seconds_total"]


def test_get_and_update_labels(store: CatalogStore) -> None:
    entry = store.get_sync("node_memory_MemAvailable_bytes")
    assert entry is not None and entry.labels == [] and not entry.labels_sampled

    store.update_labels_sync("node_memory_MemAvailable_bytes", ["instance", "job"])
    entry = store.get_sync("node_memory_MemAvailable_bytes")
    assert entry is not None and entry.labels == ["instance", "job"] and entry.labels_sampled
    # the FTS index follows
    assert "node_memory_MemAvailable_bytes" in [h.name for h in store.search_sync("instance")]

    assert store.get_sync("nope") is None


def test_status_and_meta(store: CatalogStore) -> None:
    status = store.status_sync()
    assert status.state == "idle"
    assert status.metric_count == 4
    assert status.categories == {"cpu": 1, "memory": 1, "container": 1, "prometheus": 1}

    store.set_meta_sync(
        state="ready", updated_at="2024-03-13T10:00:00+00:00", duration_seconds="1.5"
    )
    status = store.status_sync()
    assert status.state == "ready"
    assert status.updated_at is not None and status.updated_at.year == 2024
    assert status.duration_seconds == 1.5

    store.set_meta_sync(error="boom")
    assert store.status_sync().error == "boom"
    store.set_meta_sync(error=None)
    assert store.status_sync().error is None


def test_replace_all_is_atomic_replacement(store: CatalogStore) -> None:
    store.replace_all_sync([MetricEntry(name="only_one", category="other")])
    assert store.names_sync() == ["only_one"]
    assert store.search_sync("cpu") == []


def test_fts_schema_upgrade_reindexes_existing_rows(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE metrics (name TEXT PRIMARY KEY, type TEXT NOT NULL, help TEXT NOT NULL,
            unit TEXT NOT NULL, category TEXT NOT NULL, exporter TEXT, labels TEXT NOT NULL,
            labels_sampled INTEGER NOT NULL DEFAULT 0);
        CREATE VIRTUAL TABLE metrics_fts USING fts5(name, help, tokenize = 'unicode61');
        INSERT INTO metrics VALUES
            ('node_memory_MemAvailable_bytes', 'gauge', 'x', '', 'memory', 'node', '[]', 0);
        INSERT INTO metrics_fts VALUES ('node_memory_MemAvailable_bytes', 'x');
        """
    )
    conn.commit()
    conn.close()

    store = CatalogStore(path)
    assert [h.name for h in store.search_sync("available")] == ["node_memory_MemAvailable_bytes"]
