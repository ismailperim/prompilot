"""Panel spec base model and the contract every panel module implements."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, StringConstraints

from app.models import CamelModel

SPEC_VERSION = 1

# Curated subset of Grafana unit IDs. Kept small on purpose: the LLM picks
# from this list and the exporter passes the value through unchanged.
Unit = Literal[
    "none",
    "short",
    "percent",  # 0-100
    "percentunit",  # 0.0-1.0
    "bytes",  # IEC (KiB, MiB)
    "decbytes",  # SI (kB, MB)
    "Bps",
    "bps",
    "s",
    "ms",
    "ops",
    "reqps",
    "rps",
    "wps",
]

DURATION_PATTERN = r"^\d+(ms|s|m|h|d|w)$"
Duration = Annotated[str, StringConstraints(pattern=DURATION_PATTERN)]

_LEGEND_VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class Query(CamelModel):
    ref_id: Annotated[str, StringConstraints(pattern=r"^[A-Z]$")] = "A"
    expr: Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
    legend: str | None = Field(default=None, description="Grafana-style template, e.g. '{{pod}}'")
    instant: bool = False


class PanelSpec(CamelModel):
    """Declarative description of one panel. Data is never part of the spec."""

    version: Literal[1] = SPEC_VERSION
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str
    title: Annotated[str, StringConstraints(min_length=1, max_length=120, strip_whitespace=True)]
    description: str = ""
    queries: list[Query] = Field(min_length=1, max_length=8)
    unit: Unit = "short"
    time_from: Duration | None = Field(
        default=None, description="Per-panel relative range override, e.g. '24h'"
    )
    options: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PanelModule:
    """Everything the core needs to know about a panel type.

    ``to_grafana`` receives an already-validated spec and returns the
    type-specific part of a Grafana panel (``type``, ``fieldConfig``,
    ``options``). Shared fields — title, targets, unit, gridPos — are filled
    in by the exporter via :func:`grafana_panel_base`.
    """

    type: str
    description: str
    options_model: type[BaseModel]
    to_grafana: Callable[[PanelSpec], dict[str, Any]]
    default_layout: tuple[int, int] = (12, 8)  # (w, h) in Grafana grid units


def grafana_panel_base(spec: PanelSpec) -> dict[str, Any]:
    """Grafana panel fields shared by every panel type."""
    panel: dict[str, Any] = {
        "title": spec.title,
        "description": spec.description,
        "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
        "targets": [
            {
                "refId": q.ref_id,
                "expr": q.expr,
                "legendFormat": q.legend or "__auto",
                "instant": q.instant,
                "range": not q.instant,
                "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
            }
            for q in spec.queries
        ],
        "fieldConfig": {"defaults": {"unit": spec.unit}, "overrides": []},
        "options": {},
    }
    if spec.time_from:
        panel["timeFrom"] = spec.time_from
    return panel
