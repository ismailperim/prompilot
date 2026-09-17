"""Knowledge base: what is loaded, search it, reload it."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import Knowledge
from app.knowledge.service import KnowledgeStatus
from app.knowledge.store import KnowledgeHit
from app.models import CamelModel

router = APIRouter(prefix="/api/projects/{slug}/knowledge", tags=["knowledge"])


class KnowledgeSearchResponse(CamelModel):
    query: str
    hits: list[KnowledgeHit]


@router.get("", response_model=KnowledgeStatus)
async def knowledge_status(service: Knowledge) -> KnowledgeStatus:
    """Documents and operator prompt currently loaded for this project."""
    return await service.status()


@router.get("/search", response_model=KnowledgeSearchResponse)
async def search(
    service: Knowledge,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> KnowledgeSearchResponse:
    hits = await service.search(q, limit=limit)
    return KnowledgeSearchResponse(query=q, hits=hits)


@router.post("/reload", response_model=KnowledgeStatus, status_code=status.HTTP_200_OK)
async def reload(service: Knowledge) -> KnowledgeStatus:
    """Re-read the files now (they are also re-read automatically when they change)."""
    await service.reload()
    return await service.status()
