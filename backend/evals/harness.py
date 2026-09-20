"""Runs one case through the real agent loop and scores what it did."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.agent.llm import ChatProvider
from app.agent.loop import run_agent
from app.agent.tools import ToolContext
from app.catalog.builder import CatalogBuilder
from app.catalog.store import CatalogStore
from app.dashboard.service import DashboardService
from app.dashboard.store import DEFAULT_ID, DashboardStore
from app.knowledge.docstore import KnowledgeDocStore
from app.knowledge.service import KnowledgeService
from app.knowledge.store import KnowledgeStore
from app.prometheus import PrometheusClient, PrometheusError
from evals.cases import Case, Expect


@dataclass
class Result:
    case: Case
    passed: bool
    failures: list[str]
    iterations: int
    tool_calls: list[str]
    seconds: float
    answer: str
    error: str | None = None
    emitted: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Environment:
    """Shared across cases: Prometheus, a built catalog and the knowledge files."""

    prometheus: PrometheusClient
    catalog_store: CatalogStore
    catalog_builder: CatalogBuilder
    knowledge: KnowledgeService
    workdir: Path

    @classmethod
    async def create(
        cls, prometheus_url: str, workdir: Path, knowledge_dir: Path | None
    ) -> Environment:
        workdir.mkdir(parents=True, exist_ok=True)
        prometheus = PrometheusClient(prometheus_url)
        db = workdir / "catalog.sqlite"
        store = CatalogStore(db)
        builder = CatalogBuilder(prometheus, store, project="evals")
        knowledge = KnowledgeService(
            knowledge_dir or workdir / "no-knowledge", KnowledgeStore(db), KnowledgeDocStore(db)
        )
        env = cls(prometheus, store, builder, knowledge, workdir)
        status = await builder.status()
        if status.metric_count == 0:
            status = await builder.build()
            if status.error:
                raise RuntimeError(f"catalog build failed: {status.error}")
        await knowledge.reload()
        return env

    async def close(self) -> None:
        await self.prometheus.aclose()


async def run_case(
    env: Environment, provider: ChatProvider, case: Case, *, max_iterations: int = 8
) -> Result:
    db = env.workdir / f"case-{case.id}-{int(time.time() * 1000)}.sqlite"
    service = DashboardService(DashboardStore(db))
    for spec in case.panels:
        await service.add_panel(DEFAULT_ID, spec)
    dashboard = await service.get(DEFAULT_ID)
    end = datetime.now(tz=UTC)
    start = end - timedelta(hours=1)
    ctx = ToolContext(
        prometheus=env.prometheus,
        catalog_store=env.catalog_store,
        catalog_builder=env.catalog_builder,
        dashboard=service,
        dashboard_id=DEFAULT_ID,
        start=start,
        end=end,
        max_data_points=500,
        knowledge=env.knowledge,
    )
    knowledge = await env.knowledge.current()
    relevant = await env.knowledge.search(case.message, limit=3) if knowledge.documents else []

    answer = ""
    tool_calls: list[str] = []
    emitted: list[dict[str, Any]] = []
    patched: set[str] = set()
    removed: set[str] = set()
    iterations = 0
    error: str | None = None
    started = time.perf_counter()
    try:
        async for event in run_agent(
            provider=provider,
            ctx=ctx,
            dashboard=dashboard,
            catalog=await env.catalog_builder.status(),
            history=[dict(h) for h in case.history],
            user_message=case.message,
            max_iterations=max_iterations,
            knowledge=knowledge,
            relevant_notes=relevant,
        ):
            d = event.data
            match event.type:
                case "text_delta":
                    answer += str(d.get("text", ""))
                case "tool_call":
                    tool_calls.append(str(d.get("name")))
                case "panel_added":
                    emitted.append(d["panel"]["spec"])
                case "panel_updated":
                    patched.add(d["panel"]["spec"]["id"])
                case "panel_removed":
                    removed.add(str(d["id"]))
                case "error":
                    error = str(d.get("message"))
                case "done":
                    iterations = int(d.get("iterations") or 0)
                    if d.get("stopped") == "iteration_limit":
                        error = error or "iteration limit"
    except Exception as exc:  # noqa: BLE001 — a crash is a failed case, not a crashed run
        error = f"{type(exc).__name__}: {exc}"
    seconds = time.perf_counter() - started
    db.unlink(missing_ok=True)

    failures = await _score(
        env, case.expect, answer, tool_calls, emitted, patched, removed, iterations, start, end
    )
    if error:
        failures.append(f"error: {error}")
    return Result(
        case,
        not failures,
        failures,
        iterations,
        tool_calls,
        seconds,
        answer.strip(),
        error,
        emitted,
    )


async def _score(
    env: Environment,
    expect: Expect,
    answer: str,
    tool_calls: list[str],
    emitted: list[dict[str, Any]],
    patched: set[str],
    removed: set[str],
    iterations: int,
    start: datetime,
    end: datetime,
) -> list[str]:
    failures: list[str] = []
    for name in expect.tools:
        if name not in tool_calls:
            failures.append(f"tool {name} not called")
    for name in expect.no_tools:
        if name in tool_calls:
            failures.append(f"tool {name} called")
    if expect.panels is not None and len(emitted) != expect.panels:
        failures.append(f"{len(emitted)} panels emitted, expected {expect.panels}")
    if expect.panels_min is not None and len(emitted) < expect.panels_min:
        failures.append(f"{len(emitted)} panels emitted, expected at least {expect.panels_min}")
    if expect.panel_type and emitted and not any(p["type"] == expect.panel_type for p in emitted):
        failures.append(f"panel type {[p['type'] for p in emitted]}, expected {expect.panel_type}")
    if expect.unit_in and emitted and not any(p.get("unit") in expect.unit_in for p in emitted):
        failures.append(
            f"unit {[p.get('unit') for p in emitted]}, expected one of {list(expect.unit_in)}"
        )
    exprs = [q["expr"] for p in emitted for q in p.get("queries", [])]
    for pattern in expect.expr:
        if not any(re.search(pattern, e) for e in exprs):
            failures.append(f"no query matches /{pattern}/")
    for pattern in expect.expr_not:
        if any(re.search(pattern, e) for e in exprs):
            failures.append(f"a query matches forbidden /{pattern}/")
    if expect.data and emitted:
        for expr in exprs:
            if not await _has_data(env.prometheus, expr, start, end):
                failures.append(f"no data for {expr}")
    if expect.answer and not re.search(expect.answer, answer, re.I | re.S):
        failures.append(f"answer does not match /{expect.answer}/")
    if expect.lang and detect_lang(answer) != expect.lang:
        failures.append(f"answer language {detect_lang(answer)!r}, expected {expect.lang!r}")
    for pid in expect.patched:
        if pid not in patched:
            failures.append(f"panel {pid} not patched")
    for pid in expect.removed:
        if pid not in removed:
            failures.append(f"panel {pid} not removed")
    if expect.max_iterations is not None and iterations > expect.max_iterations:
        failures.append(f"{iterations} iterations, allowed {expect.max_iterations}")
    return failures


async def _has_data(
    prometheus: PrometheusClient, expr: str, start: datetime, end: datetime
) -> bool:
    try:
        result = await prometheus.query_range(expr, start=start, end=end, max_data_points=100)
    except PrometheusError:
        return False
    return bool(result.result)


# ö/ü are shared with German, so only the letters unique to each language count.
_TR = re.compile(r"[çğışİĞŞ]|\b(ve|için|olarak|panel[ie]|eklendi|kullanım|gösteriyor)\b")
_DE = re.compile(r"[äßÄ]|\b(und|der|die|das|wird|wurde|hinzugefügt|über|nicht|zeigt|ein|eine)\b")
_EN = re.compile(r"\b(the|and|added|panel|shows|is|are|with)\b")


def detect_lang(text: str) -> str:
    """Good enough to tell Turkish, German and English apart in a short answer."""
    scores = {
        "tr": len(_TR.findall(text)),
        "de": len(_DE.findall(text)),
        "en": len(_EN.findall(text)),
    }
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] else "en"


async def run_all(
    env: Environment, provider: ChatProvider, cases: list[Case], *, concurrency: int = 3
) -> list[Result]:
    semaphore = asyncio.Semaphore(concurrency)

    async def one(case: Case) -> Result:
        async with semaphore:
            return await run_case(env, provider, case)

    return list(await asyncio.gather(*(one(c) for c in cases)))
