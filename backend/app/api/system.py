"""Instance-level status for the UI."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.deps import AppSettings, Registry

router = APIRouter(prefix="/api", tags=["system"])


class LLMStatus(BaseModel):
    enabled: bool
    model: str | None = None
    provider: str = "openai"


class SystemStatus(BaseModel):
    llm: LLMStatus
    projects: int
    auth_enabled: bool = False
    version: str = "0.2.1"


@router.get("/status", response_model=SystemStatus)
async def status(settings: AppSettings, registry: Registry, request: Request) -> SystemStatus:
    """Whether an LLM is configured, how many projects exist, whether auth is on."""
    return SystemStatus(
        llm=LLMStatus(
            enabled=settings.llm_enabled, model=settings.llm_model, provider=settings.llm_provider
        ),
        projects=len(await registry.list()),
        auth_enabled=request.app.state.auth.enabled,
    )
