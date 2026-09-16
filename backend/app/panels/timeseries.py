"""Time-series panel: lines, bars or points over time. The default choice."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.models import CamelModel
from app.panels.base import PanelModule, PanelSpec, grafana_panel_base


class TimeseriesOptions(CamelModel):
    draw: Literal["line", "bars", "points"] = "line"
    stack: bool = False
    fill: float = Field(default=0.0, ge=0, le=1, description="Area fill opacity, 0 = none")
    line_width: int = Field(default=1, ge=0, le=5)
    legend: Literal["bottom", "right", "hidden"] = "bottom"
    min: float | None = Field(default=None, description="Fixed Y axis minimum")
    max: float | None = Field(default=None, description="Fixed Y axis maximum")


def to_grafana(spec: PanelSpec) -> dict[str, Any]:
    opts = TimeseriesOptions.model_validate(spec.options)
    panel = grafana_panel_base(spec)
    panel["type"] = "timeseries"

    defaults = panel["fieldConfig"]["defaults"]
    defaults["custom"] = {
        "drawStyle": opts.draw,
        "lineWidth": opts.line_width,
        "fillOpacity": round(opts.fill * 100),
        "showPoints": "always" if opts.draw == "points" else "never",
        "stacking": {"mode": "normal" if opts.stack else "none", "group": "A"},
    }
    if opts.min is not None:
        defaults["min"] = opts.min
    if opts.max is not None:
        defaults["max"] = opts.max

    panel["options"] = {
        "legend": {
            "showLegend": opts.legend != "hidden",
            "placement": "right" if opts.legend == "right" else "bottom",
            "displayMode": "list",
        },
        "tooltip": {"mode": "multi", "sort": "desc"},
    }
    return panel


MODULE = PanelModule(
    type="timeseries",
    description=(
        "Values over time as lines, bars or points; one series per label combination. "
        "The default for anything that changes over time: rates, latencies, saturation. "
        "Options: draw (line|bars|points), stack, fill (0-1), lineWidth, legend "
        "(bottom|right|hidden), min/max."
    ),
    options_model=TimeseriesOptions,
    to_grafana=to_grafana,
    default_layout=(12, 8),
)
