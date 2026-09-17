"""Anthropic Messages API with streaming, tool use and prompt caching.

The agent keeps its conversation in OpenAI's message shape; this module
translates: assistant tool calls become ``tool_use`` blocks, tool results
become ``tool_result`` blocks in a user turn, and the system prompt plus tool
definitions get ``cache_control`` so the big, stable prefix is cached across
turns and requests.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from anthropic import APIError, APITimeoutError, AsyncAnthropic

from app.agent.llm import AssistantTurn, Delta, LLMError, Message, ToolCall, ToolSchema
from app.config import Settings


def to_anthropic_tools(tools: list[ToolSchema]) -> list[dict[str, Any]]:
    out = []
    for t in tools:
        fn = t["function"]
        out.append(
            {
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            }
        )
    if out:
        out[-1]["cache_control"] = {"type": "ephemeral"}
    return out


def to_anthropic_messages(
    messages: list[Message],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split OpenAI-style messages into Anthropic ``system`` blocks and ``messages``."""
    system: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system.append({"type": "text", "text": str(m.get("content") or "")})
            continue
        if role == "user":
            out.append({"role": "user", "content": str(m.get("content") or "")})
            continue
        if role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": str(m["content"])})
            for tc in m.get("tool_calls") or []:
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": args,
                    }
                )
            out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
            continue
        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": m["tool_call_id"],
                "content": str(m.get("content") or ""),
            }
            # Consecutive tool results belong in one user turn.
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
    if system:
        system[-1]["cache_control"] = {"type": "ephemeral"}
    return system, out


class AnthropicProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float = 120,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> None:
        self.model = model
        self._client = AsyncAnthropic(
            api_key=api_key, base_url=base_url, timeout=timeout_seconds, max_retries=1
        )
        self._max_tokens = max_tokens
        self._temperature = temperature

    @classmethod
    def from_settings(cls, settings: Settings) -> AnthropicProvider:
        key = settings.anthropic_api_key or settings.llm_api_key
        assert key and settings.llm_model
        return cls(
            api_key=key,
            model=settings.llm_model,
            base_url=settings.anthropic_base_url,
            timeout_seconds=settings.llm_timeout.total_seconds(),
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )

    async def stream(
        self, messages: list[Message], tools: list[ToolSchema]
    ) -> AsyncIterator[Delta | AssistantTurn]:
        system, converted = to_anthropic_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "messages": converted,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = to_anthropic_tools(tools)

        turn = AssistantTurn()
        open_tools: dict[int, ToolCall] = {}
        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    kind = getattr(event, "type", "")
                    if kind == "content_block_start":
                        block = event.content_block
                        if getattr(block, "type", "") == "tool_use":
                            open_tools[event.index] = ToolCall(
                                id=block.id, name=block.name, arguments=""
                            )
                    elif kind == "content_block_delta":
                        delta = event.delta
                        dtype = getattr(delta, "type", "")
                        if dtype == "text_delta":
                            turn.content += delta.text
                            yield Delta("text", delta.text)
                        elif dtype == "input_json_delta":
                            call = open_tools.get(event.index)
                            if call is not None:
                                call.arguments += delta.partial_json
                        elif dtype == "thinking_delta":
                            yield Delta("reasoning", delta.thinking)
                    elif kind == "message_delta":
                        stop = getattr(event.delta, "stop_reason", None)
                        if stop:
                            turn.finish_reason = {"tool_use": "tool_calls", "end_turn": "stop"}.get(
                                stop, stop
                            )
        except APITimeoutError as exc:
            raise LLMError(f"the model did not answer within the timeout ({exc})") from exc
        except APIError as exc:
            raise LLMError(f"LLM request failed: {exc.message}") from exc

        for index in sorted(open_tools):
            call = open_tools[index]
            call.arguments = call.arguments or "{}"
            turn.tool_calls.append(call)
        yield turn
