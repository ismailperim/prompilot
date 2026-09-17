"""System prompt assembly. Everything the model needs to know, nothing it can hallucinate around."""

from __future__ import annotations

import json
from typing import get_args

from app.catalog.models import CatalogStatus
from app.dashboard.models import Dashboard
from app.knowledge.loader import Knowledge
from app.knowledge.store import KnowledgeHit
from app.panels import registry
from app.panels.base import Unit

BASE = """You are PromPilot, an assistant that turns questions about a Prometheus installation into dashboard panels.

You work in a loop with tools. For a new chart:
1. Call search_catalog to find candidate metrics. Never guess metric names — only use names returned by the catalog or already on the dashboard.
2. Write PromQL. Counters need rate(...[5m]); histograms use histogram_quantile over rate(..._bucket[5m]) summed by le; aggregate away high-cardinality labels (instance, pod) unless the user asks per-instance.
3. Call query_prometheus to dry-run the expression. If it errors or returns no series, fix the query (check label names via the catalog) and try again — at most twice.
4. Call emit_panel with the final spec. If validation fails, correct the reported fields and call it again once.
5. Answer in one or two short sentences: what the panel shows and anything worth knowing (e.g. no data yet, assumptions). Do not paste PromQL or JSON into the answer; the panel already shows it.

To change an existing panel use patch_panel with only the fields that change; to delete one use remove_panel. Refer to panels by the ids listed below.

Choose units carefully: percentunit for 0-1 ratios (e.g. rate of *_seconds_total per core), percent for 0-100, bytes for sizes, Bps for byte rates, s/ms for durations, ops/reqps for rates of events. Use legend templates like "{{instance}}" or "{{pod}}" so series are named.

Memory: when the user tells you something about their system that is not in the notes — what a service is, which namespace or label matters, an SLO, a naming rule, or a correction to something you assumed — call save_note so it is remembered next time. Keep notes short and factual; never save current metric values.

Reply in the same language the user used in their message. If they write English, answer in English; if Turkish, answer in Turkish. Do not switch languages. Metric names, PromQL and panel titles the user did not specify stay as they are. Use plain text; no Markdown headings, tables or bullet lists — at most **bold** for a panel title and `code` for a metric name.

If the request is not about metrics or dashboards, say so briefly. Keep the tone plain and technical.
"""


def panel_types_section() -> str:
    lines = ["Panel types available (type — when to use it; options):"]
    for module in registry.modules():
        schema = module.options_model.model_json_schema(by_alias=True)
        options = ", ".join(
            f"{name}{'=' + json.dumps(prop['default']) if 'default' in prop else ''}"
            for name, prop in schema.get("properties", {}).items()
        )
        lines.append(f"- {module.type} — {module.description} Options: {options}")
    lines.append(f"Units: {', '.join(get_args(Unit))}.")
    return "\n".join(lines)


def catalog_section(status: CatalogStatus) -> str:
    if status.metric_count == 0:
        return (
            f"Metric catalog: not available (state={status.state}). "
            "search_catalog will return nothing; tell the user the catalog is still building."
        )
    counts = ", ".join(f"{k} {v}" for k, v in status.categories.items())
    return f"Metric catalog: {status.metric_count} metrics. Categories: {counts}."


def dashboard_section(dashboard: Dashboard) -> str:
    if not dashboard.panels:
        return "Dashboard is empty."
    lines = [
        f'Dashboard "{dashboard.title}", time range {dashboard.time_range.from_} → {dashboard.time_range.to}. Current panels:'
    ]
    for placement in dashboard.panels:
        spec = placement.spec
        exprs = "; ".join(f"{q.ref_id}: {q.expr}" for q in spec.queries)
        lines.append(
            f'- id={spec.id} type={spec.type} unit={spec.unit} title="{spec.title}" queries: {exprs}'
        )
    return "\n".join(lines)


def knowledge_section(knowledge: Knowledge | None, relevant: list[KnowledgeHit]) -> str:
    if knowledge is None or (not knowledge.documents and not knowledge.prompt):
        return ""
    parts: list[str] = []
    if knowledge.prompt:
        parts.append(
            "Operator instructions (follow these; they describe this specific system):\n"
            + knowledge.prompt
        )
    if knowledge.documents:
        lines = []
        for d in knowledge.documents:
            heads = ", ".join(d.headings[:8]) + (", …" if len(d.headings) > 8 else "")
            lines.append(f"- {d.title}" + (f" ({heads})" if heads else ""))
        parts.append(
            "Operator notes are available via search_knowledge. Documents:\n"
            + "\n".join(lines)
            + "\nSearch them when a request mentions a service, a team term, an SLO or anything "
            "the metric names alone do not explain."
        )
    if relevant:
        notes = "\n\n".join(f"[{h.doc} › {h.heading}]\n{h.body}" for h in relevant)
        parts.append("Notes that may be relevant to the current request:\n" + notes)
    return "\n\n".join(parts)


def build_system_prompt(
    dashboard: Dashboard,
    catalog: CatalogStatus,
    knowledge: Knowledge | None = None,
    relevant_notes: list[KnowledgeHit] | None = None,
) -> str:
    sections = [BASE, panel_types_section(), catalog_section(catalog)]
    knowledge_text = knowledge_section(knowledge, relevant_notes or [])
    if knowledge_text:
        sections.append(knowledge_text)
    sections.append(dashboard_section(dashboard))
    return "\n\n".join(sections)
