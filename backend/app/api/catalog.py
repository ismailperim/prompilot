"""Metric catalog: status, search, detail, rebuild."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import Catalog, CatalogBuild
from app.catalog.categorize import CATEGORIES
from app.catalog.models import CatalogStatus, MetricEntry, SearchHit
from app.models import CamelModel

router = APIRouter(prefix="/api/projects/{slug}/catalog", tags=["catalog"])
global_router = APIRouter(prefix="/api/catalog", tags=["catalog"])


class SearchResponse(CamelModel):
    query: str
    hits: list[SearchHit]


class RebuildResponse(CamelModel):
    started: bool
    status: CatalogStatus


@router.get("/status", response_model=CatalogStatus)
async def catalog_status(builder: CatalogBuild) -> CatalogStatus:
    return await builder.status()


@global_router.get("/categories", response_model=list[str])
async def categories() -> list[str]:
    return list(CATEGORIES)


@router.get("/search", response_model=SearchResponse)
async def search(
    store: Catalog,
    q: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    category: Annotated[str | None, Query()] = None,
) -> SearchResponse:
    """Full-text search over metric names, help text, categories and label keys."""
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"unknown category {category!r}")
    hits = await store.search(q, limit=limit, category=category)
    return SearchResponse(query=q, hits=hits)


@router.get("/metrics/{name}", response_model=MetricEntry)
async def metric(name: str, store: Catalog, builder: CatalogBuild) -> MetricEntry:
    """One metric with its label keys (sampled on demand if the build skipped it)."""
    entry = await store.get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"metric {name!r} not in catalog")
    return await builder.ensure_labels(entry)


@router.post("/rebuild", response_model=RebuildResponse, status_code=status.HTTP_202_ACCEPTED)
async def rebuild(builder: CatalogBuild) -> RebuildResponse:
    """Start a rebuild in the background. Returns immediately."""
    started = builder.trigger()
    return RebuildResponse(started=started, status=await builder.status())
