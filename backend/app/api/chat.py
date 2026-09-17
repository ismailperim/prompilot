"""POST /api/chat — the agent, streamed as Server-Sent Events."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import Field

from app.agent.loop import run_agent
from app.agent.tools import ToolContext
from app.api.deps import AppSettings, Runtime
from app.dashboard.timerange import resolve
from app.models import CamelModel

router = APIRouter(prefix="/api/projects/{slug}", tags=["chat"])


class ChatMessage(CamelModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(CamelModel):
    message: str = Field(default="", max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)
    playbook: str | None = Field(
        default=None, description="Name of a playbook to run; its steps become the request"
    )
    lang: str | None = Field(
        default=None,
        max_length=16,
        description="UI language tag, e.g. tr-TR; used when the request has no language cue",
    )


_LANGUAGES = {
    "tr": "Turkish",
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
}


def _language_name(tag: str) -> str:
    return _LANGUAGES.get(tag.lower().split("-")[0], tag)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    runtime: Runtime,
    settings: AppSettings,
) -> StreamingResponse:
    """Stream agent events: text_delta, reasoning_delta, tool_call, tool_result,
    panel_added, panel_updated, panel_removed, error, done."""
    provider = getattr(request.app.state, "llm", None)
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail="No LLM configured. Set LLM_BASE_URL and LLM_MODEL to enable chat.",
        )

    service = runtime.dashboard
    dashboard = await service.get()
    catalog = await runtime.catalog_builder.status()
    start, end = resolve(dashboard.time_range)
    knowledge_service = runtime.knowledge
    knowledge = await knowledge_service.current()

    user_message = body.message.strip()
    if body.playbook:
        playbook = knowledge.playbook(body.playbook)
        if playbook is None:
            raise HTTPException(status_code=404, detail=f"playbook {body.playbook!r} not found")
        user_message = (
            f"Run the playbook “{playbook.title}”. Follow its steps in order, add the panels it "
            "asks for, and finish with the summary it describes."
            + (f" Answer in {_language_name(body.lang)}." if body.lang else "")
            + "\n\n"
            + playbook.body
            + (f"\n\nAdditional instructions from the user: {user_message}" if user_message else "")
        )
    if not user_message:
        raise HTTPException(status_code=422, detail="message or playbook is required")
    # Cheap retrieval up front: notes matching the request go straight into the prompt.
    relevant = (
        await knowledge_service.search(body.message or body.playbook or "", limit=3)
        if knowledge.documents and (body.message or body.playbook)
        else []
    )
    ctx = ToolContext(
        prometheus=runtime.prometheus,
        catalog_store=runtime.catalog_store,
        catalog_builder=runtime.catalog_builder,
        dashboard=service,
        start=start,
        end=end,
        max_data_points=settings.prometheus_max_data_points,
        knowledge=knowledge_service,
    )

    async def stream() -> AsyncIterator[str]:
        async for event in run_agent(
            provider=provider,
            ctx=ctx,
            dashboard=dashboard,
            catalog=catalog,
            history=[m.model_dump() for m in body.history],
            user_message=user_message,
            max_iterations=settings.llm_max_tool_iterations,
            history_turns=settings.llm_history_turns,
            knowledge=knowledge,
            relevant_notes=relevant,
        ):
            yield _sse(event.type, event.data)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
