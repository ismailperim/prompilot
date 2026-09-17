"""Instance-level status for the UI."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import AppSettings, Registry

router = APIRouter(prefix="/api", tags=["system"])


class LLMStatus(BaseModel):
    enabled: bool
    model: str | None = None


class SystemStatus(BaseModel):
    llm: LLMStatus
    projects: int
    version: str = "0.1.0"


@router.get("/status", response_model=SystemStatus)
async def status(settings: AppSettings, registry: Registry) -> SystemStatus:
    """Whether an LLM is configured and how many projects exist."""
    return SystemStatus(
        llm=LLMStatus(enabled=settings.llm_enabled, model=settings.llm_model),
        projects=len(await registry.list()),
    )
