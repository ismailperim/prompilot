"""POST /api/chat — the agent, streamed as Server-Sent Events."""

from __future__ import annotations

import json
import secrets
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import Field

from app.agent.loop import run_agent
from app.agent.tools import ToolContext
from app.api.deps import AppSettings, DashboardId, Runtime
from app.chat.models import ChatHistory
from app.chat.recorder import TurnRecorder
from app.dashboard.timerange import resolve
from app.models import CamelModel

router = APIRouter(prefix="/api/projects/{slug}/dashboards/{did}", tags=["chat"])


class ChatMessage(CamelModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(CamelModel):
    message: str = Field(default="", max_length=4000)
    history: list[ChatMessage] = Field(
        default_factory=list,
        max_length=40,
        description="Prior turns to condition on; when omitted the stored transcript is used",
    )
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


def _turn_id() -> str:
    return "t" + secrets.token_urlsafe(9)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/chat")
async def chat(
    did: DashboardId,
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
    dashboard = await service.get(did)
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
        dashboard_id=did,
        start=start,
        end=end,
        max_data_points=settings.prometheus_max_data_points,
        knowledge=knowledge_service,
    )

    if body.history:
        history = [m.model_dump() for m in body.history]
    else:
        stored = await runtime.chat.history(did, limit=settings.llm_history_turns * 2)
        history = [
            {"role": t.role, "content": t.content}
            for t in stored.turns
            if t.content and not t.error
        ]

    shown = (
        f"Run playbook: {knowledge.playbook(body.playbook).title}"  # type: ignore[union-attr]
        + (f" — {body.message.strip()}" if body.message.strip() else "")
        if body.playbook
        else user_message
    )
    user_turn = await runtime.chat.append(did, id=_turn_id(), role="user", content=shown)
    recorder = TurnRecorder()
    assistant_id = _turn_id()

    async def stream() -> AsyncIterator[str]:
        yield _sse("turn", {"userId": user_turn.id, "assistantId": assistant_id})
        try:
            async for event in run_agent(
                provider=provider,
                ctx=ctx,
                dashboard=dashboard,
                catalog=catalog,
                history=history,
                user_message=user_message,
                max_iterations=settings.llm_max_tool_iterations,
                history_turns=settings.llm_history_turns,
                knowledge=knowledge,
                relevant_notes=relevant,
            ):
                recorder.observe(event)
                yield _sse(event.type, event.data)
        finally:
            # Also on disconnect: whatever was produced stays in the shared transcript.
            await runtime.chat.append(
                did,
                id=assistant_id,
                role="assistant",
                content=recorder.content.strip(),
                reasoning=recorder.reasoning.strip(),
                blocks=recorder.blocks,
                error=recorder.error,
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/chat/history")
async def chat_history(
    did: DashboardId,
    runtime: Runtime,
    after: int = 0,
    limit: int = Query(default=100, ge=1, le=400),
) -> ChatHistory:
    """The dashboard's transcript, oldest first. ``after`` returns only newer turns."""
    await runtime.dashboard.get(did)
    return await runtime.chat.history(did, after=after, limit=limit)


@router.delete("/chat/history", status_code=204)
async def clear_chat_history(did: DashboardId, runtime: Runtime) -> Response:
    await runtime.chat.clear(did)
    return Response(status_code=204)
