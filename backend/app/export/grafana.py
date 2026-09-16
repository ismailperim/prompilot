"""Dashboard state → Grafana dashboard JSON.

The output is what Grafana's *Import dashboard* dialog expects: it declares a
``DS_PROMETHEUS`` input so the user picks their Prometheus datasource on
import, and every panel/target references ``${DS_PROMETHEUS}``.
"""

from __future__ import annotations

import re
from typing import Any

from app.dashboard.models import Dashboard
from app.panels import registry

# Grafana 11/12 dashboards. Older Grafana versions migrate forward on import.
SCHEMA_VERSION = 41

DATASOURCE_INPUT = {
    "name": "DS_PROMETHEUS",
    "label": "Prometheus",
    "description": "",
    "type": "datasource",
    "pluginId": "prometheus",
    "pluginName": "Prometheus",
}


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "dashboard"


def export_dashboard(dashboard: Dashboard) -> dict[str, Any]:
    panels: list[dict[str, Any]] = []
    ordered = sorted(dashboard.panels, key=lambda p: (p.layout.y, p.layout.x))
    for index, placement in enumerate(ordered, start=1):
        panel = registry.to_grafana(placement.spec)
        panel["id"] = index
        panel["gridPos"] = placement.layout.model_dump()
        panels.append(panel)

    return {
        "__inputs": [DATASOURCE_INPUT],
        "__requires": [
            {"type": "grafana", "id": "grafana", "name": "Grafana", "version": ""},
            {"type": "datasource", "id": "prometheus", "name": "Prometheus", "version": ""},
            *(
                {"type": "panel", "id": panel_type, "name": panel_type, "version": ""}
                for panel_type in sorted({p["type"] for p in panels})
            ),
        ],
        "annotations": {
            "list": [
                {
                    "builtIn": 1,
                    "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                    "enable": True,
                    "hide": True,
                    "iconColor": "rgba(0, 211, 255, 1)",
                    "name": "Annotations & Alerts",
                    "type": "dashboard",
                }
            ]
        },
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,  # shared crosshair across panels
        "id": None,
        "uid": None,
        "title": dashboard.title,
        "description": "Exported from PromPilot",
        "tags": ["prompilot"],
        "timezone": "browser",
        "schemaVersion": SCHEMA_VERSION,
        "version": 1,
        "time": {"from": dashboard.time_range.from_, "to": dashboard.time_range.to},
        "timepicker": {},
        "refresh": dashboard.refresh or "",
        "templating": {"list": []},
        "links": [],
        "panels": panels,
    }
