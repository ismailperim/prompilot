"""Agent loop tests with a scripted provider — no network, no real model."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.agent.llm import AssistantTurn, Delta, LLMError, Message, ToolCall
from app.agent.loop import AgentEvent, run_agent
from app.agent.prompts import build_system_prompt
from app.agent.tools import TOOL_SCHEMAS, ToolContext
from app.catalog.builder import CatalogBuilder
from app.catalog.models import CatalogStatus, MetricEntry
from app.catalog.store import CatalogStore
from app.dashboard.service import DashboardService
from app.dashboard.store import DashboardStore
from app.prometheus import PrometheusClient
from tests.conftest import json_response, load_fixture


class ScriptedProvider:
    """Replays a list of turns; records the messages it was given."""

    def __init__(self, turns: list[AssistantTurn | Exception]) -> None:
        self.turns = list(turns)
        self.calls: list[tuple[list[Message], list[dict[str, Any]]]] = []

    async def stream(
        self, messages: list[Message], tools: list[dict[str, Any]]
    ) -> AsyncIterator[Delta | AssistantTurn]:
        self.calls.append(([dict(m) for m in messages], tools))
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        if turn.content:
            for word in turn.content.split(" "):
                yield Delta("text", word + " ")
        yield turn


def call(name: str, **args: Any) -> ToolCall:
    return ToolCall(id=f"call_{name}", name=name, arguments=json.dumps(args))


@pytest.fixture
def ctx(tmp_path: Path) -> ToolContext:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/query_range":
            if "bad" in request.url.params.get("query", ""):
                return json_response(load_fixture("error_parse"), 400)
            if "empty" in request.url.params.get("query", ""):
                return json_response(load_fixture("empty_matrix"))
            return json_response(load_fixture("matrix"))
        if request.url.path == "/api/v1/labels":
            return json_response(
                {"status": "success", "data": ["__name__", "cpu", "instance", "job", "mode"]}
            )
        return json_response(
            {"status": "error", "errorType": "bad_data", "error": "unexpected"}, 400
        )

    prometheus = PrometheusClient("http://prom.test:9090", transport=httpx.MockTransport(handler))
    catalog_store = CatalogStore(tmp_path / "db.sqlite")
    catalog_store.replace_all_sync(
        [
            MetricEntry(
                name="node_cpu_seconds_total", type="counter", help="CPU time", category="cpu"
            ),
            MetricEntry(
                name="node_memory_MemFree_bytes",
                type="gauge",
                help="Free memory",
                category="memory",
            ),
        ]
    )
    end = datetime(2024, 1, 1, tzinfo=UTC)
    return ToolContext(
        prometheus=prometheus,
        catalog_store=catalog_store,
        catalog_builder=CatalogBuilder(prometheus, catalog_store),
        dashboard=DashboardService(DashboardStore(tmp_path / "db.sqlite")),
        start=end - timedelta(hours=1),
        end=end,
        max_data_points=200,
    )


async def collect(
    provider: ScriptedProvider, ctx: ToolContext, message: str, **kw: Any
) -> list[AgentEvent]:
    dashboard = await ctx.dashboard.get()
    catalog = await ctx.catalog_store.status()
    return [
        e
        async for e in run_agent(
            provider=provider,
            ctx=ctx,
            dashboard=dashboard,
            catalog=catalog,
            history=[],
            user_message=message,
            **kw,
        )
    ]


def types(events: list[AgentEvent]) -> list[str]:
    return [e.type for e in events]


async def test_happy_path_search_query_emit_answer(ctx: ToolContext) -> None:
    provider = ScriptedProvider(
        [
            AssistantTurn(tool_calls=[call("search_catalog", query="cpu")]),
            AssistantTurn(
                tool_calls=[call("query_prometheus", expr="rate(node_cpu_seconds_total[5m])")]
            ),
            AssistantTurn(
                tool_calls=[
                    call(
                        "emit_panel",
                        type="timeseries",
                        title="CPU per core",
                        queries=[{"expr": "rate(node_cpu_seconds_total[5m])", "legend": "{{cpu}}"}],
                        unit="percentunit",
                    )
                ]
            ),
            AssistantTurn(content="Added a CPU panel."),
        ]
    )
    events = await collect(provider, ctx, "show cpu per core")

    assert types(events) == [
        "tool_call", "tool_result",
        "tool_call", "tool_result",
        "tool_call", "panel_added", "tool_result",
        "text_delta", "text_delta", "text_delta", "text_delta",
        "done",
    ]  # fmt: skip
    search = events[1].data
    assert search["ok"] and search["result"]["metrics"][0]["name"] == "node_cpu_seconds_total"
    assert search["result"]["metrics"][0]["labels"] == [
        "cpu",
        "instance",
        "job",
        "mode",
    ]  # sampled on demand
    query = events[3].data
    assert (
        query["ok"]
        and query["result"]["seriesCount"] == 2
        and query["result"]["sample"][0]["labels"]["cpu"] == "0"
    )
    added = events[5].data["panel"]
    assert added["spec"]["title"] == "CPU per core"
    assert added["spec"]["queries"][0]["refId"] == "A"
    assert events[-1].data == {"stopped": "answered", "iterations": 4}

    dashboard = await ctx.dashboard.get()
    assert [p.spec.title for p in dashboard.panels] == ["CPU per core"]

    # Conversation was threaded correctly: tool results follow the assistant tool-call message.
    last_messages = provider.calls[-1][0]
    assert last_messages[0]["role"] == "system"
    assert last_messages[-1]["role"] == "tool"
    assert json.loads(last_messages[-1]["content"])["ok"] is True
    assert last_messages[-2]["tool_calls"][0]["function"]["name"] == "emit_panel"


async def test_validation_error_is_fed_back_and_retried(ctx: ToolContext) -> None:
    provider = ScriptedProvider(
        [
            AssistantTurn(
                tool_calls=[
                    call(
                        "emit_panel",
                        type="timeseries",
                        title="x",
                        queries=[{"expr": "up"}],
                        unit="furlongs",
                    )
                ]
            ),
            AssistantTurn(
                tool_calls=[
                    call(
                        "emit_panel",
                        type="timeseries",
                        title="x",
                        queries=[{"expr": "up"}],
                        unit="short",
                    )
                ]
            ),
            AssistantTurn(content="Done."),
        ]
    )
    events = await collect(provider, ctx, "add up")
    first = events[1].data
    assert first["ok"] is False
    assert any("unit" in p for p in first["result"]["problems"])
    assert "panel_added" in types(events)
    fed_back = json.loads(provider.calls[1][0][-1]["content"])
    assert fed_back["error"] == "invalid panel spec"


async def test_query_errors_and_empty_results_are_reported(ctx: ToolContext) -> None:
    provider = ScriptedProvider(
        [
            AssistantTurn(
                tool_calls=[
                    call("query_prometheus", expr="rate(bad"),
                    call("query_prometheus", expr="empty"),
                ]
            ),
            AssistantTurn(content="Neither works."),
        ]
    )
    events = await collect(provider, ctx, "test")
    results = [e.data for e in events if e.type == "tool_result"]
    assert results[0]["ok"] is False and "parse error" in results[0]["result"]["error"]
    assert (
        results[1]["ok"] is False
        and results[1]["result"]["seriesCount"] == 0
        and "hint" in results[1]["result"]
    )


async def test_patch_and_remove(ctx: ToolContext) -> None:
    placement = await ctx.dashboard.add_panel(
        {"type": "timeseries", "title": "Old", "queries": [{"expr": "up"}]}
    )
    provider = ScriptedProvider(
        [
            AssistantTurn(
                tool_calls=[
                    call(
                        "patch_panel",
                        id=placement.spec.id,
                        changes={"title": "New", "options": {"draw": "bars"}},
                    )
                ]
            ),
            AssistantTurn(
                tool_calls=[
                    call("remove_panel", id=placement.spec.id),
                    call("remove_panel", id="ghost"),
                ]
            ),
            AssistantTurn(content="Updated then removed."),
        ]
    )
    events = await collect(provider, ctx, "rename then remove")
    assert events[1].type == "panel_updated" and events[1].data["panel"]["spec"]["title"] == "New"
    assert events[1].data["panel"]["spec"]["options"]["draw"] == "bars"
    assert "panel_removed" in types(events)
    ghost = [e for e in events if e.type == "tool_result"][-1].data
    assert ghost["ok"] is False and "ghost" in ghost["result"]["error"]
    assert (await ctx.dashboard.get()).panels == []


async def test_unknown_tool_and_bad_json_arguments(ctx: ToolContext) -> None:
    provider = ScriptedProvider(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall(id="1", name="fly", arguments="{}"),
                    ToolCall(id="2", name="search_catalog", arguments="{not json"),
                ]
            ),
            AssistantTurn(content="ok"),
        ]
    )
    events = await collect(provider, ctx, "x")
    results = [e.data for e in events if e.type == "tool_result"]
    assert "unknown tool" in results[0]["result"]["error"]
    assert "not valid JSON" in results[1]["result"]["error"]


async def test_iteration_limit_withholds_tools_on_last_round(ctx: ToolContext) -> None:
    provider = ScriptedProvider(
        [AssistantTurn(tool_calls=[call("search_catalog", query="cpu")]) for _ in range(3)]
    )
    events = await collect(provider, ctx, "loop forever", max_iterations=3)
    assert events[-2].type == "error" and "too many tool calls" in events[-2].data["message"]
    assert events[-1].data["stopped"] == "iteration_limit"
    assert provider.calls[0][1] == TOOL_SCHEMAS
    assert provider.calls[-1][1] == []  # last round: no tools → must answer in text


async def test_llm_error_is_surfaced(ctx: ToolContext) -> None:
    provider = ScriptedProvider([LLMError("the model did not answer within the timeout")])
    events = await collect(provider, ctx, "hi")
    assert types(events) == ["error", "done"]
    assert "timeout" in events[0].data["message"]


async def test_history_is_trimmed_to_plain_text_turns(ctx: ToolContext) -> None:
    provider = ScriptedProvider([AssistantTurn(content="hi")])
    dashboard = await ctx.dashboard.get()
    history: list[Message] = [
        {"role": "user", "content": f"q{i}"}
        if i % 2 == 0
        else {"role": "assistant", "content": f"a{i}"}
        for i in range(10)
    ]
    history.append({"role": "tool", "content": "should be dropped"})
    events = [
        e
        async for e in run_agent(
            provider=provider,
            ctx=ctx,
            dashboard=dashboard,
            catalog=CatalogStatus(),
            history=history,
            user_message="now",
            history_turns=2,
        )
    ]
    assert events[-1].type == "done"
    sent = provider.calls[0][0]
    assert [m["content"] for m in sent[1:-1]] == ["q6", "a7", "q8", "a9"]
    assert sent[-1] == {"role": "user", "content": "now"}


async def test_system_prompt_lists_panels_types_and_catalog(ctx: ToolContext) -> None:
    await ctx.dashboard.add_panel(
        {"type": "timeseries", "title": "CPU", "queries": [{"expr": "up"}]}
    )
    prompt = build_system_prompt(await ctx.dashboard.get(), await ctx.catalog_store.status())
    assert "timeseries —" in prompt
    assert "percentunit" in prompt
    assert "Metric catalog: 2 metrics" in prompt
    assert 'title="CPU" queries: A: up' in prompt

    empty = build_system_prompt(await ctx.dashboard.get(), CatalogStatus(state="building"))
    assert "not available (state=building)" in empty


def test_tool_schemas_are_flat_and_valid_json() -> None:
    text = json.dumps(TOOL_SCHEMAS)
    assert "oneOf" not in text and "anyOf" not in text and "$ref" not in text
    names = [t["function"]["name"] for t in TOOL_SCHEMAS]
    assert names == [
        "search_catalog",
        "search_knowledge",
        "query_prometheus",
        "emit_panel",
        "patch_panel",
        "remove_panel",
    ]


async def test_repeated_read_only_calls_are_served_from_memory(ctx: ToolContext) -> None:
    provider = ScriptedProvider(
        [
            AssistantTurn(
                tool_calls=[
                    ToolCall(
                        id="a", name="search_catalog", arguments='{"query": "cpu", "limit": 10}'
                    ),
                    ToolCall(
                        id="b", name="search_catalog", arguments='{"limit": 10, "query": "cpu"}'
                    ),
                ]
            ),
            AssistantTurn(content="ok"),
        ]
    )
    calls_before = len(await ctx.catalog_store.search("cpu"))
    events = await collect(provider, ctx, "x")
    results = [e.data for e in events if e.type == "tool_result"]
    assert len(results) == 2
    assert results[0]["result"] == results[1]["result"]
    assert calls_before >= 1


def test_prompt_asks_for_the_users_language() -> None:
    from app.agent.prompts import BASE

    assert "language the user writes in" in BASE
