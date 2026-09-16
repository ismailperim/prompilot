"""Metric catalog: status, search, detail, rebuild."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.catalog.builder import CatalogBuilder
from app.catalog.categorize import CATEGORIES
from app.catalog.models import CatalogStatus, MetricEntry, SearchHit
from app.catalog.store import CatalogStore
from app.models import CamelModel

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def _builder(request: Request) -> CatalogBuilder:
    return request.app.state.catalog_builder


def _store(request: Request) -> CatalogStore:
    return request.app.state.catalog_store


class SearchResponse(CamelModel):
    query: str
    hits: list[SearchHit]


class RebuildResponse(CamelModel):
    started: bool
    status: CatalogStatus


@router.get("/status", response_model=CatalogStatus)
async def catalog_status(request: Request) -> CatalogStatus:
    return await _builder(request).status()


@router.get("/categories", response_model=list[str])
async def categories() -> list[str]:
    return list(CATEGORIES)


@router.get("/search", response_model=SearchResponse)
async def search(
    request: Request,
    q: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    category: Annotated[str | None, Query()] = None,
) -> SearchResponse:
    """Full-text search over metric names, help text, categories and label keys."""
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"unknown category {category!r}")
    hits = await _store(request).search(q, limit=limit, category=category)
    return SearchResponse(query=q, hits=hits)


@router.get("/metrics/{name}", response_model=MetricEntry)
async def metric(request: Request, name: str) -> MetricEntry:
    """One metric with its label keys (sampled on demand if the build skipped it)."""
    entry = await _store(request).get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"metric {name!r} not in catalog")
    return await _builder(request).ensure_labels(entry)


@router.post("/rebuild", response_model=RebuildResponse, status_code=status.HTTP_202_ACCEPTED)
async def rebuild(request: Request) -> RebuildResponse:
    """Start a rebuild in the background. Returns immediately."""
    builder = _builder(request)
    started = builder.trigger()
    return RebuildResponse(started=started, status=await builder.status())
