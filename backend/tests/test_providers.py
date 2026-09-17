"""Provider adapters, exercised without network: message/tool conversion and stream handling."""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from app.agent.llm import AssistantTurn, Delta, LLMError, OpenAICompatibleProvider
from app.agent.providers import build_provider
from app.agent.providers.anthropic import (
    AnthropicProvider,
    to_anthropic_messages,
    to_anthropic_tools,
)
from app.agent.providers.azure import AzureOpenAIProvider
from app.agent.providers.gemini import GeminiProvider, to_gemini_contents, to_gemini_tools
from app.agent.tools import TOOL_SCHEMAS
from app.config import Settings

CONVERSATION: list[dict[str, Any]] = [
    {"role": "system", "content": "You are PromPilot."},
    {"role": "user", "content": "cpu per core"},
    {
        "role": "assistant",
        "content": "Looking it up.",
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "search_catalog", "arguments": '{"query": "cpu"}'},
            },
            {
                "id": "c2",
                "type": "function",
                "function": {"name": "query_prometheus", "arguments": '{"expr": "up"}'},
            },
        ],
    },
    {"role": "tool", "tool_call_id": "c1", "content": '{"count": 1}'},
    {"role": "tool", "tool_call_id": "c2", "content": "not json"},
    {"role": "user", "content": "thanks"},
]


async def collect(
    provider: Any, messages: list[dict[str, Any]]
) -> tuple[str, AssistantTurn, list[Delta]]:
    deltas: list[Delta] = []
    turn: AssistantTurn | None = None
    async for item in provider.stream(messages, TOOL_SCHEMAS):
        if isinstance(item, Delta):
            deltas.append(item)
        else:
            turn = item
    assert turn is not None
    return "".join(d.text for d in deltas if d.kind == "text"), turn, deltas


# ---- Anthropic ----------------------------------------------------------------


class TestAnthropicConversion:
    def test_messages(self) -> None:
        system, messages = to_anthropic_messages(CONVERSATION)
        assert system == [
            {"type": "text", "text": "You are PromPilot.", "cache_control": {"type": "ephemeral"}}
        ]
        assert messages[0] == {"role": "user", "content": "cpu per core"}
        assistant = messages[1]
        assert assistant["role"] == "assistant"
        assert assistant["content"][0] == {"type": "text", "text": "Looking it up."}
        assert assistant["content"][1] == {
            "type": "tool_use",
            "id": "c1",
            "name": "search_catalog",
            "input": {"query": "cpu"},
        }
        # both tool results land in ONE user turn, in order
        results = messages[2]
        assert results["role"] == "user"
        assert [b["tool_use_id"] for b in results["content"]] == ["c1", "c2"]
        assert results["content"][1]["content"] == "not json"
        assert messages[3] == {"role": "user", "content": "thanks"}

    def test_tools_get_input_schema_and_cache_marker(self) -> None:
        tools = to_anthropic_tools(TOOL_SCHEMAS)
        assert tools[0]["name"] == "search_catalog"
        assert tools[0]["input_schema"]["type"] == "object"
        assert "cache_control" not in tools[0]
        assert tools[-1]["cache_control"] == {"type": "ephemeral"}


class FakeAnthropicStream:
    def __init__(self, events: list[Any]) -> None:
        self._events = events

    async def __aenter__(self) -> FakeAnthropicStream:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def __aiter__(self) -> AsyncIterator[Any]:
        async def gen() -> AsyncIterator[Any]:
            for e in self._events:
                yield e

        return gen()


def ns(**kw: Any) -> SimpleNamespace:
    return SimpleNamespace(**kw)


async def test_anthropic_stream_assembles_text_and_tool_use() -> None:
    events = [
        ns(type="message_start"),
        ns(type="content_block_start", index=0, content_block=ns(type="text")),
        ns(type="content_block_delta", index=0, delta=ns(type="text_delta", text="Let me ")),
        ns(type="content_block_delta", index=0, delta=ns(type="text_delta", text="look.")),
        ns(
            type="content_block_start",
            index=1,
            content_block=ns(type="tool_use", id="toolu_1", name="search_catalog"),
        ),
        ns(
            type="content_block_delta",
            index=1,
            delta=ns(type="input_json_delta", partial_json='{"query": '),
        ),
        ns(
            type="content_block_delta",
            index=1,
            delta=ns(type="input_json_delta", partial_json='"cpu"}'),
        ),
        ns(type="content_block_delta", index=1, delta=ns(type="thinking_delta", thinking="hmm")),
        ns(type="message_delta", delta=ns(stop_reason="tool_use")),
    ]
    provider = AnthropicProvider(api_key="k", model="claude-test")
    provider._client = ns(messages=ns(stream=lambda **kwargs: FakeAnthropicStream(events)))  # type: ignore[assignment]

    text, turn, deltas = await collect(provider, CONVERSATION)
    assert text == "Let me look."
    assert [c.name for c in turn.tool_calls] == ["search_catalog"]
    assert turn.tool_calls[0].id == "toolu_1"
    assert json.loads(turn.tool_calls[0].arguments) == {"query": "cpu"}
    assert turn.finish_reason == "tool_calls"
    assert any(d.kind == "reasoning" and d.text == "hmm" for d in deltas)


async def test_anthropic_passes_system_tools_and_settings() -> None:
    seen: dict[str, Any] = {}

    def stream(**kwargs: Any) -> FakeAnthropicStream:
        seen.update(kwargs)
        return FakeAnthropicStream([ns(type="message_delta", delta=ns(stop_reason="end_turn"))])

    provider = AnthropicProvider(api_key="k", model="claude-test", max_tokens=123, temperature=0.5)
    provider._client = ns(messages=ns(stream=stream))  # type: ignore[assignment]
    _, turn, _ = await collect(provider, CONVERSATION)
    assert (
        seen["model"] == "claude-test" and seen["max_tokens"] == 123 and seen["temperature"] == 0.5
    )
    assert seen["system"][0]["text"] == "You are PromPilot."
    assert [t["name"] for t in seen["tools"]][:2] == ["search_catalog", "search_knowledge"]
    assert turn.finish_reason == "stop" and turn.tool_calls == []


async def test_anthropic_api_errors_become_llm_errors() -> None:
    import anthropic

    def stream(**kwargs: Any) -> Any:
        raise anthropic.APIConnectionError(request=ns())

    provider = AnthropicProvider(api_key="k", model="m")
    provider._client = ns(messages=ns(stream=stream))  # type: ignore[assignment]
    with pytest.raises(LLMError):
        await collect(provider, CONVERSATION)


# ---- Gemini -------------------------------------------------------------------


class TestGeminiConversion:
    def test_contents(self) -> None:
        system, contents = to_gemini_contents(CONVERSATION)
        assert system == "You are PromPilot."
        assert contents[0].role == "user" and contents[0].parts[0].text == "cpu per core"  # type: ignore[index]
        model = contents[1]
        assert model.role == "model"
        assert model.parts[0].text == "Looking it up."  # type: ignore[index]
        assert model.parts[1].function_call.name == "search_catalog"  # type: ignore[index,union-attr]
        assert model.parts[1].function_call.args == {"query": "cpu"}  # type: ignore[index,union-attr]
        responses = contents[2]
        assert responses.role == "user"
        assert [p.function_response.name for p in responses.parts] == [
            "search_catalog",
            "query_prometheus",
        ]  # type: ignore[union-attr]
        assert responses.parts[0].function_response.response == {"count": 1}  # type: ignore[index,union-attr]
        assert responses.parts[1].function_response.response == {"result": "not json"}  # type: ignore[index,union-attr]
        assert contents[3].parts[0].text == "thanks"  # type: ignore[index]

    def test_tools(self) -> None:
        tools = to_gemini_tools(TOOL_SCHEMAS)
        assert len(tools) == 1
        decls = tools[0].function_declarations or []
        assert decls[0].name == "search_catalog"
        assert decls[0].parameters_json_schema["type"] == "object"  # type: ignore[index]


async def test_gemini_stream_mints_tool_call_ids() -> None:
    chunks = [
        ns(
            candidates=[
                ns(
                    content=ns(parts=[ns(text="Checking", thought=False, function_call=None)]),
                    finish_reason=None,
                )
            ]
        ),
        ns(
            candidates=[
                ns(
                    content=ns(
                        parts=[
                            ns(
                                text=None,
                                thought=False,
                                function_call=ns(
                                    id=None, name="search_catalog", args={"query": "cpu"}
                                ),
                                thought_signature=b"sig-1",
                            ),
                            ns(
                                text=None,
                                thought=False,
                                function_call=ns(
                                    id=None, name="query_prometheus", args={"expr": "up"}
                                ),
                            ),
                        ]
                    ),
                    finish_reason="STOP",
                )
            ]
        ),
    ]

    async def gen() -> AsyncIterator[Any]:
        for c in chunks:
            yield c

    async def generate_content_stream(**kwargs: Any) -> AsyncIterator[Any]:
        assert kwargs["model"] == "gemini-test"
        assert kwargs["config"].system_instruction == "You are PromPilot."
        return gen()

    provider = GeminiProvider(model="gemini-test", api_key="k")
    provider._client = ns(aio=ns(models=ns(generate_content_stream=generate_content_stream)))  # type: ignore[assignment]
    text, turn, _ = await collect(provider, CONVERSATION)
    assert text == "Checking"
    assert [c.name for c in turn.tool_calls] == ["search_catalog", "query_prometheus"]
    assert turn.tool_calls[0].id == "call_1" and turn.tool_calls[1].id == "call_2"
    assert json.loads(turn.tool_calls[1].arguments) == {"expr": "up"}
    assert turn.finish_reason == "tool_calls"
    # Gemini 3 thought signatures round-trip through the history message
    assert turn.tool_calls[0].signature == base64.b64encode(b"sig-1").decode()
    assert turn.tool_calls[1].signature is None
    message = turn.as_message()
    assert message["tool_calls"][0]["signature"] == "c2lnLTE="
    assert "signature" not in message["tool_calls"][1]
    _, contents = to_gemini_contents([{"role": "system", "content": "s"}, message])
    assert contents[0].parts[1].thought_signature == b"sig-1"  # type: ignore[index]
    assert contents[0].parts[2].thought_signature is None  # type: ignore[index]


# ---- factory & settings ---------------------------------------------------------


def test_llm_enabled_per_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "m")
    assert Settings(_env_file=None).llm_enabled is False  # openai needs a base url

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert Settings(_env_file=None).llm_enabled is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert Settings(_env_file=None).llm_enabled is True

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert Settings(_env_file=None).llm_enabled is False
    monkeypatch.setenv("GEMINI_USE_VERTEX", "true")
    assert Settings(_env_file=None).llm_enabled is True

    monkeypatch.setenv("LLM_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://x.openai.azure.com")
    assert Settings(_env_file=None).llm_enabled is False
    monkeypatch.setenv("LLM_API_KEY", "k")
    assert Settings(_env_file=None).llm_enabled is True


def test_build_provider_picks_the_class(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "m")
    assert build_provider(Settings(_env_file=None)) is None

    monkeypatch.setenv("LLM_BASE_URL", "http://llm/v1")
    assert isinstance(build_provider(Settings(_env_file=None)), OpenAICompatibleProvider)

    monkeypatch.setenv("LLM_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://x.openai.azure.com")
    monkeypatch.setenv("LLM_API_KEY", "k")
    provider = build_provider(Settings(_env_file=None))
    assert isinstance(provider, AzureOpenAIProvider) and provider.model == "m"

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert isinstance(build_provider(Settings(_env_file=None)), AnthropicProvider)

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert isinstance(build_provider(Settings(_env_file=None)), GeminiProvider)
