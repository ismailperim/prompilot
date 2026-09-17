"""Table panel: one row per series, a column per label, and the value. For top-N and inventories."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.models import CamelModel
from app.panels.base import PanelModule, PanelSpec, grafana_panel_base


class TableOptions(CamelModel):
    sort_by: str | None = Field(
        default=None, description="Column to sort by: 'value' or a label name such as 'pod'"
    )
    sort_desc: bool = True
    limit: int = Field(default=100, ge=1, le=1000, description="Max rows shown")
    hide_columns: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Label columns to hide, e.g. ['job', 'instance']",
    )
    value_column: str = Field(
        default="Value", max_length=40, description="Header for the value column"
    )


def to_grafana(spec: PanelSpec) -> dict[str, Any]:
    opts = TableOptions.model_validate(spec.options)
    panel = grafana_panel_base(spec)
    panel["type"] = "table"
    for target in panel["targets"]:
        target["instant"] = True
        target["range"] = False
        target["format"] = "table"

    exclude = {"Time": True, "__name__": True, **{c: True for c in opts.hide_columns}}
    rename = {"Value": opts.value_column} if opts.value_column != "Value" else {}
    transformations: list[dict[str, Any]] = [
        {
            "id": "organize",
            "options": {"excludeByName": exclude, "renameByName": rename, "indexByName": {}},
        }
    ]
    if opts.sort_by:
        name = opts.value_column if opts.sort_by.lower() == "value" else opts.sort_by
        transformations.append(
            {"id": "sortBy", "options": {"sort": [{"field": name, "desc": opts.sort_desc}]}}
        )
    transformations.append({"id": "limit", "options": {"limitField": opts.limit}})
    panel["transformations"] = transformations
    panel["options"] = {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}
    return panel


MODULE = PanelModule(
    type="table",
    description=(
        "Rows of label values with a number: which pods use the most memory, disk usage per "
        "mountpoint, targets that are down. Queries run as instant queries at the end of the "
        "range (set instant=true), so use a rate() or aggregation that yields one value per "
        "series, and topk(N, …) for top-N. Options: sortBy ('value' or a label), sortDesc, "
        "limit, hideColumns, valueColumn."
    ),
    options_model=TableOptions,
    to_grafana=to_grafana,
    default_layout=(12, 8),
)
