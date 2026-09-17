import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent.prompts import build_system_prompt
from app.catalog.models import CatalogStatus
from app.config import get_settings
from app.dashboard.models import Dashboard
from app.knowledge.loader import load_knowledge, parse_document
from app.knowledge.service import KnowledgeService
from app.knowledge.store import KnowledgeStore
from app.main import create_app
from tests.conftest import P

DOC = """# Checkout service

Handles payments. Owned by team Pay.

## Latency SLO

p99 of `checkout_request_duration_seconds` must stay under 300 ms.
Use histogram_quantile over rate(..._bucket[5m]).

## Queue depth

`checkout_queue_depth` is a gauge; above 500 means workers are falling behind.

### Alerting

Page when depth > 800 for 10 minutes.
"""


def test_parse_document_splits_on_headings(tmp_path: Path) -> None:
    path = tmp_path / "checkout.md"
    path.write_text(DOC)
    doc = parse_document(path, DOC)

    assert doc.title == "Checkout service"
    assert doc.headings == ["Latency SLO", "Queue depth", "Alerting"]
    assert [c.heading for c in doc.chunks] == [
        "Checkout service",
        "Latency SLO",
        "Queue depth",
        "Queue depth › Alerting",
    ]
    assert "Owned by team Pay" in doc.chunks[0].body
    assert "300 ms" in doc.chunks[1].body


def test_long_sections_are_split_on_paragraphs(tmp_path: Path) -> None:
    text = "# Big\n\n## Section\n\n" + "\n\n".join(f"paragraph {i} " + "x" * 400 for i in range(10))
    (tmp_path / "big.md").write_text(text)
    doc = parse_document(tmp_path / "big.md", text)
    assert len(doc.chunks) > 1
    assert all(len(c.body) <= 1800 for c in doc.chunks)
    assert all(c.heading == "Section" for c in doc.chunks)


def test_load_knowledge_separates_prompt_from_documents(tmp_path: Path) -> None:
    (tmp_path / "prompt.md").write_text("Always prefer per-service breakdowns.\n")
    (tmp_path / "checkout.md").write_text(DOC)
    (tmp_path / "notes.txt").write_text("ignored")

    knowledge = load_knowledge(tmp_path)
    assert knowledge.prompt == "Always prefer per-service breakdowns."
    assert [d.name for d in knowledge.documents] == ["checkout"]
    assert len(knowledge.signature) == 2  # both .md files, not the .txt


def test_missing_directory_is_empty(tmp_path: Path) -> None:
    knowledge = load_knowledge(tmp_path / "nope")
    assert knowledge.prompt is None and knowledge.documents == [] and knowledge.signature == ()


async def test_service_indexes_and_reloads_on_change(tmp_path: Path) -> None:
    kdir = tmp_path / "knowledge"
    kdir.mkdir()
    (kdir / "checkout.md").write_text(DOC)
    service = KnowledgeService(kdir, KnowledgeStore(tmp_path / "db.sqlite"))

    hits = await service.search("latency slo")
    assert hits and hits[0].heading == "Latency SLO"
    assert "300 ms" in hits[0].body

    status = await service.status()
    assert status.prompt_loaded is False
    assert status.documents[0].title == "Checkout service"
    assert status.chunks == 4

    # Edit the file: the next call notices the new mtime and re-indexes.
    time.sleep(0.01)
    (kdir / "checkout.md").write_text(DOC + "\n## Retries\n\nRetries are capped at 3.\n")
    os.utime(kdir / "checkout.md", (time.time() + 5, time.time() + 5))
    hits = await service.search("retries capped")
    assert hits and hits[0].heading == "Retries"


async def test_search_falls_back_to_any_word(tmp_path: Path) -> None:
    kdir = tmp_path / "knowledge"
    kdir.mkdir()
    (kdir / "checkout.md").write_text(DOC)
    service = KnowledgeService(kdir, KnowledgeStore(tmp_path / "db.sqlite"))
    hits = await service.search("queue elephants")
    assert hits and "queue" in hits[0].heading.lower()


def test_system_prompt_includes_operator_prompt_toc_and_relevant_notes(tmp_path: Path) -> None:
    (tmp_path / "prompt.md").write_text("Speak like an SRE. Latency SLO is 300 ms.")
    (tmp_path / "checkout.md").write_text(DOC)
    knowledge = load_knowledge(tmp_path)
    store = KnowledgeStore(tmp_path / "db.sqlite")
    store.replace_all_sync(knowledge.chunks)
    relevant = store.search_sync("queue depth", limit=2)

    prompt = build_system_prompt(Dashboard(), CatalogStatus(), knowledge, relevant)
    assert "Operator instructions" in prompt and "Speak like an SRE" in prompt
    assert "- Checkout service (Latency SLO, Queue depth, Alerting)" in prompt
    assert "Notes that may be relevant" in prompt and "falling behind" in prompt

    bare = build_system_prompt(Dashboard(), CatalogStatus())
    assert "Operator" not in bare


@pytest.fixture
def kclient(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    kdir = tmp_path / "knowledge"
    kdir.mkdir()
    (kdir / "checkout.md").write_text(DOC)
    (kdir / "prompt.md").write_text("Be brief.")
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom.test:9090")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("KNOWLEDGE_DIR", str(kdir))
    monkeypatch.setenv("CATALOG_AUTOSTART", "false")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            yield client
    finally:
        get_settings.cache_clear()


def test_knowledge_api(kclient: TestClient) -> None:
    status = kclient.get(f"{P}/knowledge").json()
    assert status["promptLoaded"] is True
    assert [d["title"] for d in status["documents"]] == ["Checkout service"]
    assert status["chunks"] == 4

    hits = kclient.get(f"{P}/knowledge/search", params={"q": "slo"}).json()["hits"]
    assert hits[0]["heading"] == "Latency SLO"

    assert kclient.post(f"{P}/knowledge/reload").status_code == 200
    assert kclient.get(f"{P}/knowledge/search", params={"q": ""}).status_code == 422


PLAYBOOK = """# Host health check

Quick look at whether the single demo host is healthy.

1. Add a stat panel with the 1-minute load average.
2. Add a timeseries panel of memory used.
3. Summarise in two sentences.
"""

NOTES = """# Metric notes

- `node_load1` — 1-minute load average; on this 12-core box anything above 12 is saturation.
- `node_memory_MemAvailable_bytes`: memory that can be handed out without swapping.
* `up` - 1 when the scrape succeeded
"""


def test_metric_notes_and_playbooks_are_parsed(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text(NOTES)
    (tmp_path / "playbooks").mkdir()
    (tmp_path / "playbooks" / "host-health.md").write_text(PLAYBOOK)

    knowledge = load_knowledge(tmp_path)
    notes = knowledge.metric_notes
    assert set(notes) == {"node_load1", "node_memory_MemAvailable_bytes", "up"}
    assert notes["node_load1"].text.startswith("1-minute load average")
    assert notes["up"].text == "1 when the scrape succeeded"

    assert [p.name for p in knowledge.playbooks] == ["host-health"]
    pb = knowledge.playbooks[0]
    assert pb.title == "Host health check"
    assert pb.description == "Quick look at whether the single demo host is healthy."
    assert "1. Add a stat panel" in pb.body
    # playbooks are not indexed as documents
    assert [d.name for d in knowledge.documents] == ["notes"]
    assert len(knowledge.signature) == 2


def test_project_playbook_overrides_shared(tmp_path: Path) -> None:
    shared = tmp_path / "playbooks"
    shared.mkdir()
    (shared / "check.md").write_text("# Shared check\n\nshared body\n")
    project = tmp_path / "proj" / "playbooks"
    project.mkdir(parents=True)
    (project / "check.md").write_text("# Project check\n\nproject body\n")
    knowledge = load_knowledge([tmp_path, tmp_path / "proj"])
    assert [p.title for p in knowledge.playbooks] == ["Project check"]


def test_catalog_search_carries_metric_notes(kclient: TestClient) -> None:
    from app.catalog.models import MetricEntry

    kdir = Path(kclient.get(f"{P}/knowledge").json()["directory"].split(", ")[0])
    (kdir / "notes.md").write_text(NOTES)
    store = kclient.app.state.projects._runtimes["default"].catalog_store  # type: ignore[attr-defined]
    store.replace_all_sync(
        [MetricEntry(name="node_load1", type="gauge", help="1m load", category="cpu")]
    )

    hits = kclient.get(f"{P}/catalog/search", params={"q": "load"}).json()["hits"]
    assert hits[0]["note"].startswith("1-minute load average")
    status = kclient.get(f"{P}/knowledge").json()
    assert status["metricNotes"] == 3
