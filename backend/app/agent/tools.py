"""Tools the agent can call. Flat JSON schemas (no oneOf) for maximum model compatibility."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, get_args

from app.catalog.builder import CatalogBuilder
from app.catalog.categorize import CATEGORIES
from app.catalog.store import CatalogStore
from app.dashboard.service import DashboardService, PanelNotFoundError
from app.panels import PanelValidationError, registry
from app.panels.base import Unit
from app.prometheus import PrometheusClient, PrometheusError

UNIT_VALUES = list(get_args(Unit))

MAX_SAMPLE_SERIES = 5


@dataclass(slots=True)
class ToolOutcome:
    """What a tool returns to the model, plus side effects the UI should hear about."""

    result: dict[str, Any]
    ok: bool = True
    summary: str = ""
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


@dataclass(slots=True)
class ToolContext:
    prometheus: PrometheusClient
    catalog_store: CatalogStore
    catalog_builder: CatalogBuilder
    dashboard: DashboardService
    start: datetime
    end: datetime
    max_data_points: int


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": "Search the metric catalog by keywords (metric names, help text, label names). Returns metric name, type, help, category and label keys.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords, e.g. 'cpu idle' or 'http request duration'",
                    },
                    "category": {
                        "type": "string",
                        "enum": list(CATEGORIES),
                        "description": "Optional category filter",
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_prometheus",
            "description": "Dry-run a PromQL expression against the current dashboard time range. Returns the number of series, a few sample series with labels and last value, warnings, or the error message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expr": {"type": "string", "description": "PromQL expression"},
                    "instant": {
                        "type": "boolean",
                        "default": False,
                        "description": "Instant query at the end of the range instead of a range query",
                    },
                },
                "required": ["expr"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "emit_panel",
            "description": "Add a new panel to the dashboard. Validates the spec; on failure returns the errors so you can fix them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": registry.types()},
                    "title": {"type": "string", "maxLength": 120},
                    "description": {"type": "string"},
                    "queries": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "items": {
                            "type": "object",
                            "properties": {
                                "expr": {"type": "string"},
                                "legend": {
                                    "type": "string",
                                    "description": "Legend template, e.g. '{{instance}}'",
                                },
                                "instant": {"type": "boolean", "default": False},
                            },
                            "required": ["expr"],
                        },
                    },
                    "unit": {"type": "string", "enum": UNIT_VALUES, "default": "short"},
                    "timeFrom": {
                        "type": "string",
                        "description": "Optional per-panel range override such as '24h'",
                    },
                    "options": {
                        "type": "object",
                        "description": "Panel-type options as listed in the system prompt",
                        "additionalProperties": True,
                    },
                },
                "required": ["type", "title", "queries", "unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch_panel",
            "description": "Change an existing panel. Pass only the top-level spec fields that change (title, queries, unit, options, description, timeFrom). options merge with the existing ones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Panel id from the dashboard listing"},
                    "changes": {"type": "object", "additionalProperties": True},
                },
                "required": ["id", "changes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_panel",
            "description": "Remove a panel from the dashboard.",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        },
    },
]


def _ref_ids(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign refIds A, B, C… so the model never has to."""
    out = []
    for index, query in enumerate(queries):
        q = {k: v for k, v in dict(query).items() if k != "refId"}
        q["refId"] = chr(ord("A") + index)
        out.append(q)
    return out


async def search_catalog(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    query = str(args.get("query", ""))
    limit = max(1, min(int(args.get("limit", 10) or 10), 30))
    category = args.get("category") or None
    if category and category not in CATEGORIES:
        category = None
    hits = await ctx.catalog_store.search(query, limit=limit, category=category)
    # Make sure the top hits carry label keys: the model needs them to write selectors/legends.
    enriched = [await ctx.catalog_builder.ensure_labels(hit) for hit in hits[:5]] + hits[5:]
    result = {
        "count": len(enriched),
        "metrics": [
            {
                "name": h.name,
                "type": h.type,
                "help": h.help,
                "category": h.category,
                "labels": h.labels,
            }
            for h in enriched
        ],
    }
    if not enriched:
        result["hint"] = "No match. Try a shorter or different keyword, or a category filter."
    return ToolOutcome(result=result, summary=f"{len(enriched)} metrics for “{query}”")


async def query_prometheus(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    expr = str(args.get("expr", "")).strip()
    if not expr:
        return ToolOutcome(
            result={"error": "expr is required"}, ok=False, summary="empty expression"
        )
    instant = bool(args.get("instant", False))
    try:
        if instant:
            res = await ctx.prometheus.query(expr, time=ctx.end)
        else:
            res = await ctx.prometheus.query_range(
                expr, start=ctx.start, end=ctx.end, max_data_points=min(ctx.max_data_points, 200)
            )
    except PrometheusError as exc:
        return ToolOutcome(result={"error": str(exc)}, ok=False, summary=f"error: {exc}")

    series = res.result if isinstance(res.result, list) else [res.result]
    samples = []
    if res.result_type in ("matrix", "vector"):
        for entry in series[:MAX_SAMPLE_SERIES]:
            labels = {k: v for k, v in entry.get("metric", {}).items() if k != "__name__"}
            if res.result_type == "matrix":
                values = entry.get("values", [])
                last = values[-1][1] if values else None
                points = len(values)
            else:
                last = entry.get("value", [None, None])[1]
                points = 1
            samples.append({"labels": labels, "lastValue": last, "points": points})
    elif res.result_type == "scalar":
        samples.append({"labels": {}, "lastValue": res.result[1], "points": 1})

    count = len(series) if res.result_type in ("matrix", "vector") else 1
    result: dict[str, Any] = {
        "resultType": res.result_type,
        "seriesCount": count,
        "sample": samples,
    }
    if res.warnings:
        result["warnings"] = res.warnings
    if count == 0:
        result["hint"] = (
            "No series. Check the metric name and label matchers with search_catalog, "
            "or widen the selector."
        )
    return ToolOutcome(result=result, ok=count > 0, summary=f"{count} series")


async def emit_panel(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    spec = {
        k: v
        for k, v in args.items()
        if k in {"type", "title", "description", "queries", "unit", "timeFrom", "options"}
    }
    if isinstance(spec.get("queries"), list):
        spec["queries"] = _ref_ids(spec["queries"])
    try:
        placement = await ctx.dashboard.add_panel(spec)
    except PanelValidationError as exc:
        return ToolOutcome(
            result={"error": "invalid panel spec", "problems": exc.errors},
            ok=False,
            summary="validation failed",
        )
    payload = placement.model_dump(by_alias=True)
    return ToolOutcome(
        result={"ok": True, "id": placement.spec.id, "title": placement.spec.title},
        summary=f"added “{placement.spec.title}”",
        events=[("panel_added", {"panel": payload})],
    )


async def patch_panel(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    panel_id = str(args.get("id", ""))
    changes = args.get("changes")
    if not isinstance(changes, dict):
        return ToolOutcome(
            result={"error": "changes must be an object"}, ok=False, summary="bad arguments"
        )
    changes = {k: v for k, v in changes.items() if k not in {"id", "version", "type"}}
    if isinstance(changes.get("queries"), list):
        changes["queries"] = _ref_ids(changes["queries"])
    try:
        placement = await ctx.dashboard.patch_panel(panel_id, changes)
    except PanelNotFoundError:
        return ToolOutcome(
            result={"error": f"no panel with id {panel_id!r}"}, ok=False, summary="panel not found"
        )
    except PanelValidationError as exc:
        return ToolOutcome(
            result={"error": "invalid changes", "problems": exc.errors},
            ok=False,
            summary="validation failed",
        )
    return ToolOutcome(
        result={"ok": True, "id": placement.spec.id, "title": placement.spec.title},
        summary=f"updated “{placement.spec.title}”",
        events=[("panel_updated", {"panel": placement.model_dump(by_alias=True)})],
    )


async def remove_panel(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    panel_id = str(args.get("id", ""))
    try:
        await ctx.dashboard.remove_panel(panel_id)
    except PanelNotFoundError:
        return ToolOutcome(
            result={"error": f"no panel with id {panel_id!r}"}, ok=False, summary="panel not found"
        )
    return ToolOutcome(
        result={"ok": True}, summary="removed", events=[("panel_removed", {"id": panel_id})]
    )


ToolFn = Callable[[ToolContext, dict[str, Any]], Awaitable[ToolOutcome]]

TOOLS: dict[str, ToolFn] = {
    "search_catalog": search_catalog,
    "query_prometheus": query_prometheus,
    "emit_panel": emit_panel,
    "patch_panel": patch_panel,
    "remove_panel": remove_panel,
}


async def run_tool(ctx: ToolContext, name: str, arguments: str) -> ToolOutcome:
    fn = TOOLS.get(name)
    if fn is None:
        return ToolOutcome(
            result={"error": f"unknown tool {name!r}"}, ok=False, summary="unknown tool"
        )
    try:
        args = json.loads(arguments) if arguments.strip() else {}
        if not isinstance(args, dict):
            raise ValueError("arguments must be an object")
    except ValueError as exc:
        return ToolOutcome(
            result={"error": f"arguments are not valid JSON: {exc}"},
            ok=False,
            summary="bad arguments",
        )
    return await fn(ctx, args)
