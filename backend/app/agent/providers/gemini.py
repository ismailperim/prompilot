"""Gemini through the google-genai SDK: API key (AI Studio) or Vertex AI.

Gemini's function calls carry no ids of their own, so we mint ``call_<n>``
ids for the loop and answer with ``function_response`` parts matched by
name, in order — which is how Gemini pairs them.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import errors, types

from app.agent.llm import AssistantTurn, Delta, LLMError, Message, ToolCall, ToolSchema
from app.config import Settings


def to_gemini_tools(tools: list[ToolSchema]) -> list[types.Tool]:
    declarations = [
        types.FunctionDeclaration(
            name=t["function"]["name"],
            description=t["function"].get("description", ""),
            parameters_json_schema=t["function"].get("parameters", {"type": "object"}),
        )
        for t in tools
    ]
    return [types.Tool(function_declarations=declarations)] if declarations else []


def to_gemini_contents(messages: list[Message]) -> tuple[str | None, list[types.Content]]:
    """Split OpenAI-style messages into a system instruction and Gemini contents."""
    system: list[str] = []
    contents: list[types.Content] = []
    call_names: dict[str, str] = {}  # tool_call_id → function name, for responses
    for m in messages:
        role = m["role"]
        if role == "system":
            system.append(str(m.get("content") or ""))
        elif role == "user":
            contents.append(
                types.Content(role="user", parts=[types.Part(text=str(m.get("content") or ""))])
            )
        elif role == "assistant":
            parts: list[types.Part] = []
            if m.get("content"):
                parts.append(types.Part(text=str(m["content"])))
            for tc in m.get("tool_calls") or []:
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                call_names[tc["id"]] = tc["function"]["name"]
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(name=tc["function"]["name"], args=args)
                    )
                )
            contents.append(types.Content(role="model", parts=parts or [types.Part(text="")]))
        elif role == "tool":
            name = call_names.get(m.get("tool_call_id", ""), "tool")
            raw = str(m.get("content") or "")
            try:
                payload: Any = json.loads(raw)
            except ValueError:
                payload = raw
            response = payload if isinstance(payload, dict) else {"result": payload}
            part = types.Part(
                function_response=types.FunctionResponse(name=name, response=response)
            )
            if (
                contents
                and contents[-1].role == "user"
                and contents[-1].parts
                and contents[-1].parts[0].function_response
            ):
                contents[-1].parts.append(part)  # type: ignore[union-attr]
            else:
                contents.append(types.Content(role="user", parts=[part]))
    return ("\n\n".join(system) or None), contents


class GeminiProvider:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        vertex: bool = False,
        project: str | None = None,
        location: str | None = None,
        timeout_seconds: float = 120,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> None:
        self.model = model
        options = types.HttpOptions(timeout=int(timeout_seconds * 1000))
        if vertex:
            self._client = genai.Client(
                vertexai=True, project=project, location=location, http_options=options
            )
        else:
            self._client = genai.Client(api_key=api_key, http_options=options)
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._counter = 0

    @classmethod
    def from_settings(cls, settings: Settings) -> GeminiProvider:
        assert settings.llm_model
        return cls(
            model=settings.llm_model,
            api_key=settings.gemini_api_key or settings.llm_api_key,
            vertex=settings.gemini_use_vertex,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
            timeout_seconds=settings.llm_timeout.total_seconds(),
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )

    async def stream(
        self, messages: list[Message], tools: list[ToolSchema]
    ) -> AsyncIterator[Delta | AssistantTurn]:
        system, contents = to_gemini_contents(messages)
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self._temperature,
            max_output_tokens=self._max_tokens,
            tools=to_gemini_tools(tools) or None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        turn = AssistantTurn()
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self.model, contents=contents, config=config
            )
            async for chunk in stream:
                candidates = getattr(chunk, "candidates", None) or []
                if not candidates:
                    continue
                candidate = candidates[0]
                content = getattr(candidate, "content", None)
                for part in getattr(content, "parts", None) or []:
                    if getattr(part, "thought", False) and part.text:
                        yield Delta("reasoning", part.text)
                    elif part.text:
                        turn.content += part.text
                        yield Delta("text", part.text)
                    elif part.function_call is not None:
                        self._counter += 1
                        turn.tool_calls.append(
                            ToolCall(
                                id=part.function_call.id or f"call_{self._counter}",
                                name=part.function_call.name or "",
                                arguments=json.dumps(part.function_call.args or {}),
                            )
                        )
                reason = getattr(candidate, "finish_reason", None)
                if reason:
                    turn.finish_reason = "tool_calls" if turn.tool_calls else "stop"
        except errors.APIError as exc:
            raise LLMError(f"LLM request failed: {exc.message}") from exc
        except TimeoutError as exc:
            raise LLMError("the model did not answer within the timeout") from exc
        yield turn
