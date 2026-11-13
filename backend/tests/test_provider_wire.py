"""Native providers driven through the real SDKs, with only the HTTP layer mocked.

The other provider tests replace the SDK client with fakes, which cannot notice
an SDK release that renames or drops a parameter. These run the actual
``anthropic`` / ``google-genai`` request and SSE-parsing code.
"""

from __future__ import annotations

import json
from typing import Any

import httpx2
import pytest
from anthropic import DefaultAsyncHttpxClient
from openai import DefaultAsyncHttpxClient as OpenAIHttpClient

from app.agent.llm import AssistantTurn, Delta, LLMError, Message, OpenAICompatibleProvider
from app.agent.providers.anthropic import AnthropicProvider
from app.agent.providers.gemini import GeminiProvider
from app.agent.tools import TOOL_SCHEMAS


def _sse(events: list[tuple[str | None, dict[str, Any]]]) -> bytes:
    out = []
    for name, data in events:
        prefix = f"event: {name}\n" if name else ""
        out.append(f"{prefix}data: {json.dumps(data)}\n\n")
    return "".join(out).encode()


def _stream_response(body: bytes) -> httpx2.Response:
    return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)


ANTHROPIC_EVENTS: list[tuple[str | None, dict[str, Any]]] = [
    (
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-test",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        },
    ),
    (
        "content_block_start",
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    ),
    (
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Looking"},
        },
    ),
    ("content_block_stop", {"type": "content_block_stop", "index": 0}),
    (
        "content_block_start",
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {
                "type": "tool_use",
                "id": "tu_1",
                "name": "search_catalog",
                "input": {},
            },
        },
    ),
    (
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"query": "cpu"}'},
        },
    ),
    ("content_block_stop", {"type": "content_block_stop", "index": 1}),
    (
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use", "stop_sequence": None},
            "usage": {"output_tokens": 5},
        },
    ),
    ("message_stop", {"type": "message_stop"}),
]

GEMINI_EVENTS: list[tuple[str | None, dict[str, Any]]] = [
    (None, {"candidates": [{"content": {"role": "model", "parts": [{"text": "Looking"}]}}]}),
    (
        None,
        {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {"functionCall": {"name": "search_catalog", "args": {"query": "cpu"}}}
                        ],
                    },
                    "finishReason": "STOP",
                }
            ]
        },
    ),
]


async def _collect(provider: Any) -> tuple[str, AssistantTurn]:
    text = ""
    final: AssistantTurn | None = None
    async for item in provider.stream([Message(role="user", content="show cpu")], TOOL_SCHEMAS):
        if isinstance(item, Delta) and item.kind == "text":
            text += item.text
        elif isinstance(item, AssistantTurn):
            final = item
    assert final is not None
    return text, final


async def test_anthropic_through_the_sdk() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return _stream_response(_sse(ANTHROPIC_EVENTS))

    provider = AnthropicProvider(
        api_key="k",
        model="claude-test",
        base_url="https://anthropic.test",
        http_client=DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    text, turn = await _collect(provider)

    assert text == "Looking"
    assert [(c.name, json.loads(c.arguments)) for c in turn.tool_calls] == [
        ("search_catalog", {"query": "cpu"})
    ]
    assert turn.finish_reason == "tool_calls"
    body = json.loads(requests[0].content)
    assert requests[0].url.path == "/v1/messages"
    assert body["stream"] is True and body["model"] == "claude-test"
    # The Messages API rejects sampling parameters; none may be sent.
    assert not {"temperature", "top_p", "top_k"} & body.keys()


async def test_anthropic_connection_failure_is_an_llm_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    provider = AnthropicProvider(
        api_key="k",
        model="claude-test",
        base_url="https://anthropic.test",
        http_client=DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    with pytest.raises(LLMError):
        await _collect(provider)


async def test_gemini_through_the_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_GENAI_API_VERSION", raising=False)
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return _stream_response(_sse(GEMINI_EVENTS))

    provider = GeminiProvider(
        model="gemini-test",
        api_key="k",
        async_client_args={"transport": httpx2.MockTransport(handler)},
    )
    text, turn = await _collect(provider)

    assert text == "Looking"
    assert [(c.name, json.loads(c.arguments)) for c in turn.tool_calls] == [
        ("search_catalog", {"query": "cpu"})
    ]
    assert turn.finish_reason == "tool_calls"
    # Stays on the beta endpoint, where every model alias exists.
    assert requests[0].url.path == "/v1beta/models/gemini-test:streamGenerateContent"
    body = json.loads(requests[0].content)
    assert body["tools"][0]["functionDeclarations"]


async def test_gemini_api_version_can_be_chosen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_API_VERSION", "v1")
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return _stream_response(_sse(GEMINI_EVENTS))

    provider = GeminiProvider(
        model="gemini-test",
        api_key="k",
        async_client_args={"transport": httpx2.MockTransport(handler)},
    )
    await _collect(provider)
    assert requests[0].url.path.startswith("/v1/models/")


async def test_gemini_connection_failure_is_an_llm_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    provider = GeminiProvider(
        model="gemini-test",
        api_key="k",
        async_client_args={"transport": httpx2.MockTransport(handler)},
    )
    with pytest.raises(LLMError, match="cannot reach the model endpoint"):
        await _collect(provider)


OPENAI_CHUNKS: list[tuple[str | None, dict[str, Any]]] = [
    (
        None,
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "m",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Looking"}}],
        },
    ),
    (
        None,
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "m",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "search_catalog", "arguments": '{"query": '},
                            }
                        ]
                    },
                }
            ],
        },
    ),
    (
        None,
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "m",
            "choices": [
                {
                    "index": 0,
                    "delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"cpu"}'}}]},
                    "finish_reason": "tool_calls",
                }
            ],
        },
    ),
]


def _openai(handler: Any) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url="https://gateway.test/v1",
        api_key="k",
        model="m",
        temperature=0.3,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        http_client=OpenAIHttpClient(transport=httpx2.MockTransport(handler)),
    )


async def test_openai_compatible_through_the_sdk() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        body = _sse(OPENAI_CHUNKS) + b"data: [DONE]\n\n"
        return _stream_response(body)

    text, turn = await _collect(_openai(handler))
    assert text == "Looking"
    assert [(c.name, json.loads(c.arguments)) for c in turn.tool_calls] == [
        ("search_catalog", {"query": "cpu"})
    ]
    assert turn.finish_reason == "tool_calls"
    body = json.loads(requests[0].content)
    assert requests[0].url.path == "/v1/chat/completions"
    assert body["temperature"] == 0.3 and body["stream"] is True
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["tools"][0]["function"]["name"]


async def test_openai_error_keeps_the_gateway_explanation() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            401, json={"detail": "The request could not be authenticated.", "status": 401}
        )

    with pytest.raises(LLMError) as info:
        await _collect(_openai(handler))
    assert "401" in str(info.value)
    assert "The request could not be authenticated." in str(info.value)
