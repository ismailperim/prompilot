"""Knowledge base: what is loaded, search it, reload it."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import Field

from app.api.deps import Knowledge
from app.knowledge.docstore import slugify_name, valid_name
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


class DocBody(CamelModel):
    body: str = Field(max_length=200_000)


class DocCreate(CamelModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(default="", max_length=200_000)


class DocOut(CamelModel):
    name: str
    body: str
    source: str


class PromptBody(CamelModel):
    prompt: str | None = Field(default=None, max_length=20_000)


@router.get("/docs/{name}", response_model=DocOut)
async def get_doc(name: str, service: Knowledge) -> DocOut:
    """A stored (editable) document. File-based documents are not served here."""
    found = await service.get_doc(name)
    if found is None:
        raise HTTPException(status_code=404, detail=f"no editable document {name!r}")
    body, source = found
    return DocOut(name=name, body=body, source=source)


@router.post("/docs", response_model=DocOut, status_code=status.HTTP_201_CREATED)
async def create_doc(data: DocCreate, service: Knowledge) -> DocOut:
    name = slugify_name(data.title)
    if await service.get_doc(name) is not None:
        raise HTTPException(status_code=409, detail=f"document {name!r} already exists")
    body = data.body if data.body.strip() else f"# {data.title.strip()}\n\n"
    await service.put_doc(name, body)
    return DocOut(name=name, body=body, source="ui")


@router.put("/docs/{name}", response_model=DocOut)
async def put_doc(name: str, data: DocBody, service: Knowledge) -> DocOut:
    if not valid_name(name):
        raise HTTPException(
            status_code=422, detail="name must be lowercase letters, digits and dashes"
        )
    found = await service.get_doc(name)
    source = found[1] if found else "ui"
    await service.put_doc(name, data.body, source)
    return DocOut(name=name, body=data.body, source=source)


@router.delete("/docs/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_doc(name: str, service: Knowledge) -> Response:
    if not await service.delete_doc(name):
        raise HTTPException(status_code=404, detail=f"no editable document {name!r}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/prompt", response_model=KnowledgeStatus)
async def put_prompt(data: PromptBody, service: Knowledge) -> KnowledgeStatus:
    """The project's standing instructions (appended after any prompt.md files)."""
    await service.set_prompt(data.prompt)
    return await service.status()
