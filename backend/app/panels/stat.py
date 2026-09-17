"""Stat panel: one big number per series (current, mean, max…) with an optional sparkline."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.models import CamelModel
from app.panels.base import PanelModule, PanelSpec, grafana_panel_base

Reduce = Literal["last", "mean", "max", "min", "sum"]
ThresholdColor = Literal["green", "yellow", "orange", "red", "blue", "purple"]

_GRAFANA_CALC = {"last": "lastNotNull", "mean": "mean", "max": "max", "min": "min", "sum": "sum"}


class Threshold(CamelModel):
    value: float
    color: ThresholdColor


class StatOptions(CamelModel):
    reduce: Reduce = Field(default="last", description="How to collapse the series into one number")
    color_mode: Literal["none", "value", "background"] = "value"
    graph: bool = Field(default=True, description="Show a sparkline of the range behind the value")
    decimals: int | None = Field(default=None, ge=0, le=6)
    thresholds: list[Threshold] = Field(
        default_factory=list,
        max_length=4,
        description="Ascending values; each color applies from its value upwards. Base is green.",
    )


def to_grafana(spec: PanelSpec) -> dict[str, Any]:
    opts = StatOptions.model_validate(spec.options)
    panel = grafana_panel_base(spec)
    panel["type"] = "stat"

    steps: list[dict[str, Any]] = [{"color": "green", "value": None}]
    steps.extend(
        {"color": t.color, "value": t.value} for t in sorted(opts.thresholds, key=lambda t: t.value)
    )
    defaults = panel["fieldConfig"]["defaults"]
    defaults["thresholds"] = {"mode": "absolute", "steps": steps}
    defaults["color"] = {"mode": "thresholds"}
    if opts.decimals is not None:
        defaults["decimals"] = opts.decimals

    panel["options"] = {
        "reduceOptions": {"calcs": [_GRAFANA_CALC[opts.reduce]], "fields": "", "values": False},
        "colorMode": opts.color_mode,
        "graphMode": "area" if opts.graph else "none",
        "justifyMode": "auto",
        "orientation": "auto",
        "textMode": "auto",
        "wideLayout": True,
    }
    return panel


MODULE = PanelModule(
    type="stat",
    description=(
        "A single number per series — the current (or mean/max/min/sum) value, big, with an "
        "optional sparkline. Pick for 'how much right now' questions: free disk, request rate, "
        "uptime, error count. Use thresholds to colour it (e.g. red above 90). Prefer one "
        "series or a handful; for many series use a table. Options: reduce "
        "(last|mean|max|min|sum), colorMode (none|value|background), graph, decimals, "
        "thresholds [{value, color}]."
    ),
    options_model=StatOptions,
    to_grafana=to_grafana,
    default_layout=(6, 4),
)
