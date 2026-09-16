"""Dashboard state: panels with their grid placement plus shared settings."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models import CamelModel
from app.panels.base import Duration, PanelSpec

DASHBOARD_VERSION = 1
GRID_COLUMNS = 24  # Grafana's grid, so export is lossless


class TimeRange(CamelModel):
    """Grafana-style time range: ``now-1h``, ``now``, ISO-8601 or epoch milliseconds."""

    from_: str = Field(default="now-1h", alias="from")
    to: str = "now"


class Layout(CamelModel):
    x: int = Field(ge=0, lt=GRID_COLUMNS)
    y: int = Field(ge=0)
    w: int = Field(ge=1, le=GRID_COLUMNS)
    h: int = Field(ge=1, le=200)


class PanelPlacement(CamelModel):
    spec: PanelSpec
    layout: Layout


class Dashboard(CamelModel):
    version: Literal[1] = DASHBOARD_VERSION
    title: str = Field(default="Overview", min_length=1, max_length=120)
    time_range: TimeRange = Field(default_factory=TimeRange)
    refresh: Duration | None = "30s"
    panels: list[PanelPlacement] = Field(default_factory=list)

    def find(self, panel_id: str) -> PanelPlacement | None:
        return next((p for p in self.panels if p.spec.id == panel_id), None)


class DashboardSettings(CamelModel):
    """Partial update of dashboard-level settings."""

    title: str | None = Field(default=None, min_length=1, max_length=120)
    time_range: TimeRange | None = None
    refresh: Duration | None = None
    clear_refresh: bool = False


class LayoutUpdate(CamelModel):
    id: str
    layout: Layout
