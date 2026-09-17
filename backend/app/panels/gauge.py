"""Gauge panel: the current value of a bounded quantity on a dial (0–100 %, 0–max)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from app.models import CamelModel
from app.panels.base import PanelModule, PanelSpec, grafana_panel_base
from app.panels.stat import _GRAFANA_CALC, Reduce, Threshold


class GaugeOptions(CamelModel):
    min: float = Field(default=0, description="Left end of the dial")
    max: float = Field(
        default=1, description="Right end of the dial; 1 for percentunit, 100 for percent"
    )
    reduce: Reduce = Field(default="last", description="How to collapse the series into one number")
    decimals: int | None = Field(default=None, ge=0, le=6)
    thresholds: list[Threshold] = Field(
        default_factory=list,
        max_length=4,
        description="Ascending values; each color applies from its value upwards. Base is green.",
    )
    show_threshold_markers: Literal[True, False] = True

    @model_validator(mode="after")
    def _range(self) -> GaugeOptions:
        if self.max <= self.min:
            raise ValueError("max must be greater than min")
        return self


def to_grafana(spec: PanelSpec) -> dict[str, Any]:
    opts = GaugeOptions.model_validate(spec.options)
    panel = grafana_panel_base(spec)
    panel["type"] = "gauge"

    steps: list[dict[str, Any]] = [{"color": "green", "value": None}]
    steps.extend(
        {"color": t.color, "value": t.value} for t in sorted(opts.thresholds, key=lambda t: t.value)
    )
    defaults = panel["fieldConfig"]["defaults"]
    defaults["min"] = opts.min
    defaults["max"] = opts.max
    defaults["thresholds"] = {"mode": "absolute", "steps": steps}
    defaults["color"] = {"mode": "thresholds"}
    if opts.decimals is not None:
        defaults["decimals"] = opts.decimals

    panel["options"] = {
        "reduceOptions": {"calcs": [_GRAFANA_CALC[opts.reduce]], "fields": "", "values": False},
        "showThresholdLabels": False,
        "showThresholdMarkers": opts.show_threshold_markers,
        "orientation": "auto",
    }
    return panel


MODULE = PanelModule(
    type="gauge",
    description=(
        "A dial showing where the current value sits between min and max — for bounded "
        "quantities: CPU or memory utilisation (0–1 with percentunit), disk fill, queue "
        "depth against a capacity. Always set max to the real bound; use thresholds for "
        "warning/critical colours. One dial per series, so aggregate to a few series. "
        "Options: min, max, reduce (last|mean|max|min|sum), decimals, thresholds "
        "[{value, color}], showThresholdMarkers."
    ),
    options_model=GaugeOptions,
    to_grafana=to_grafana,
    default_layout=(6, 5),
)
