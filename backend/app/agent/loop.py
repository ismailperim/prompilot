"""The agent loop: model turn → tool calls → tool results → model turn … → final answer."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.agent.llm import AssistantTurn, ChatProvider, Delta, LLMError, Message
from app.agent.prompts import build_system_prompt
from app.agent.tools import TOOL_SCHEMAS, ToolContext, run_tool
from app.catalog.models import CatalogStatus
from app.dashboard.models import Dashboard

log = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentEvent:
    type: str
    data: dict[str, Any]


def _trim_history(history: list[Message], turns: int) -> list[Message]:
    """Keep the last N user/assistant pairs and drop anything that is not plain text."""
    clean = [
        {"role": m["role"], "content": str(m.get("content") or "")}
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    return clean[-(2 * turns) :]


async def run_agent(
    *,
    provider: ChatProvider,
    ctx: ToolContext,
    dashboard: Dashboard,
    catalog: CatalogStatus,
    history: list[Message],
    user_message: str,
    max_iterations: int = 8,
    history_turns: int = 10,
) -> AsyncIterator[AgentEvent]:
    messages: list[Message] = [
        {"role": "system", "content": build_system_prompt(dashboard, catalog)},
        *_trim_history(history, history_turns),
        {"role": "user", "content": user_message},
    ]

    for iteration in range(max_iterations):
        final_round = iteration == max_iterations - 1
        turn: AssistantTurn | None = None
        try:
            # On the last allowed round, withhold tools so the model has to answer in text.
            async for item in provider.stream(messages, [] if final_round else TOOL_SCHEMAS):
                if isinstance(item, Delta):
                    yield AgentEvent(
                        "text_delta" if item.kind == "text" else "reasoning_delta",
                        {"text": item.text},
                    )
                else:
                    turn = item
        except LLMError as exc:
            yield AgentEvent("error", {"message": str(exc)})
            yield AgentEvent("done", {"stopped": "error"})
            return

        if turn is None:
            yield AgentEvent("error", {"message": "the model returned an empty response"})
            yield AgentEvent("done", {"stopped": "error"})
            return

        messages.append(turn.as_message())
        if not turn.tool_calls:
            yield AgentEvent("done", {"stopped": "answered", "iterations": iteration + 1})
            return

        for call in turn.tool_calls:
            yield AgentEvent(
                "tool_call",
                {"id": call.id, "name": call.name, "arguments": _safe_args(call.arguments)},
            )
            outcome = await run_tool(ctx, call.name, call.arguments)
            for event_type, data in outcome.events:
                yield AgentEvent(event_type, data)
            yield AgentEvent(
                "tool_result",
                {
                    "id": call.id,
                    "name": call.name,
                    "ok": outcome.ok,
                    "summary": outcome.summary,
                    "result": outcome.result,
                },
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(outcome.result, default=str),
                }
            )

    yield AgentEvent(
        "error", {"message": "stopped after too many tool calls without a final answer"}
    )
    yield AgentEvent("done", {"stopped": "iteration_limit"})


def _safe_args(raw: str) -> Any:
    try:
        return json.loads(raw) if raw.strip() else {}
    except ValueError:
        return raw
