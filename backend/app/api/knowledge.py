"""Knowledge base: what is loaded, search it, reload it."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.knowledge.service import KnowledgeService, KnowledgeStatus
from app.knowledge.store import KnowledgeHit
from app.models import CamelModel

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _service(request: Request) -> KnowledgeService:
    return request.app.state.knowledge


class KnowledgeSearchResponse(CamelModel):
    query: str
    hits: list[KnowledgeHit]


@router.get("", response_model=KnowledgeStatus)
async def knowledge_status(request: Request) -> KnowledgeStatus:
    """Documents and operator prompt currently loaded from KNOWLEDGE_DIR."""
    return await _service(request).status()


@router.get("/search", response_model=KnowledgeSearchResponse)
async def search(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> KnowledgeSearchResponse:
    hits = await _service(request).search(q, limit=limit)
    return KnowledgeSearchResponse(query=q, hits=hits)


@router.post("/reload", response_model=KnowledgeStatus, status_code=status.HTTP_200_OK)
async def reload(request: Request) -> KnowledgeStatus:
    """Re-read the files now (they are also re-read automatically when they change)."""
    service = _service(request)
    await service.reload()
    return await service.status()
