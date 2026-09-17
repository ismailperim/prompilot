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
from app.api.deps import AppSettings, Dashboards, Prometheus
from app.dashboard.timerange import resolve
from app.models import CamelModel

router = APIRouter(prefix="/api", tags=["chat"])


class ChatMessage(CamelModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(CamelModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    service: Dashboards,
    prometheus: Prometheus,
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

    dashboard = await service.get()
    catalog = await request.app.state.catalog_builder.status()
    start, end = resolve(dashboard.time_range)
    knowledge_service = request.app.state.knowledge
    knowledge = await knowledge_service.current()
    # Cheap retrieval up front: notes matching the request go straight into the prompt.
    relevant = await knowledge_service.search(body.message, limit=3) if knowledge.documents else []
    ctx = ToolContext(
        prometheus=prometheus,
        catalog_store=request.app.state.catalog_store,
        catalog_builder=request.app.state.catalog_builder,
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
            user_message=body.message,
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
