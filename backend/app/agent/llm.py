"""Thin LLM access layer.

``ChatProvider`` is the only surface the agent loop depends on; the OpenAI
implementation covers every OpenAI-compatible server (OpenAI, Ollama, vLLM,
LM Studio, OpenRouter, ...). Native cloud SDKs can be added as further
providers without touching the loop.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from openai import APIError, APITimeoutError, AsyncOpenAI

from app.config import Settings

Message = dict[str, Any]
ToolSchema = dict[str, Any]


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text as produced by the model
    # Opaque provider token that must travel back with the call (Gemini's thought signature).
    signature: str | None = None

    def parsed(self) -> dict[str, Any]:
        if not self.arguments.strip():
            return {}
        value = json.loads(self.arguments)
        if not isinstance(value, dict):
            raise ValueError("tool arguments must be a JSON object")
        return value


@dataclass(slots=True)
class Delta:
    kind: Literal["text", "reasoning"]
    text: str


@dataclass(slots=True)
class AssistantTurn:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None

    def as_message(self) -> Message:
        message: Message = {"role": "assistant", "content": self.content or None}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments or "{}"},
                    **({"signature": tc.signature} if tc.signature else {}),
                }
                for tc in self.tool_calls
            ]
        return message


class LLMError(Exception):
    """The model endpoint failed or timed out; message is safe to show to users."""


class ChatProvider(Protocol):
    async def stream(
        self, messages: list[Message], tools: list[ToolSchema]
    ) -> AsyncIterator[Delta | AssistantTurn]:
        """Yield text/reasoning deltas as they arrive, then exactly one final ``AssistantTurn``."""
        ...


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_seconds: float = 120,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "not-needed",  # local servers ignore it, the SDK requires one
            timeout=timeout_seconds,
            max_retries=1,
        )
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._extra_body = extra_body or {}

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAICompatibleProvider:
        assert settings.llm_base_url and settings.llm_model
        return cls(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout.total_seconds(),
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            extra_body=settings.llm_extra_body_json,
        )

    async def stream(
        self, messages: list[Message], tools: list[ToolSchema]
    ) -> AsyncIterator[Delta | AssistantTurn]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if self._extra_body:
            kwargs["extra_body"] = self._extra_body

        turn = AssistantTurn()
        calls: dict[int, ToolCall] = {}
        try:
            response = await self._client.chat.completions.create(**kwargs)
            async for chunk in response:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta is None:
                    continue
                if delta.content:
                    turn.content += delta.content
                    yield Delta("text", delta.content)
                # vLLM / DeepSeek / Qwen expose chain-of-thought as reasoning_content.
                reasoning = getattr(delta, "reasoning_content", None) or (
                    delta.model_extra or {}
                ).get("reasoning_content")
                if reasoning:
                    yield Delta("reasoning", str(reasoning))
                for tc in delta.tool_calls or []:
                    current = calls.setdefault(tc.index, ToolCall(id="", name="", arguments=""))
                    if tc.id:
                        current.id = tc.id
                    if tc.function:
                        if tc.function.name:
                            current.name += tc.function.name
                        if tc.function.arguments:
                            current.arguments += tc.function.arguments
                if choice.finish_reason:
                    turn.finish_reason = choice.finish_reason
        except APITimeoutError as exc:
            raise LLMError(f"the model did not answer within the timeout ({exc})") from exc
        except APIError as exc:
            raise LLMError(f"LLM request failed: {exc.message}") from exc

        for index in sorted(calls):
            call = calls[index]
            if not call.id:
                call.id = f"call_{index}"
            if call.name:
                turn.tool_calls.append(call)
        yield turn
