from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.models import CamelModel

CatalogState = Literal["idle", "building", "ready", "error"]


class MetricEntry(CamelModel):
    name: str
    type: str = "unknown"  # counter | gauge | histogram | summary | unknown
    help: str = ""
    unit: str = ""
    category: str = "other"
    exporter: str | None = None
    labels: list[str] = []
    labels_sampled: bool = False


class CatalogStatus(CamelModel):
    state: CatalogState = "idle"
    metric_count: int = 0
    updated_at: datetime | None = None
    duration_seconds: float | None = None
    error: str | None = None
    categories: dict[str, int] = {}


class SearchHit(MetricEntry):
    score: float = 0.0
