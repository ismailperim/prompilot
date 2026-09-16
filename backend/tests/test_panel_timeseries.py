import json
from pathlib import Path

from app.panels import registry
from tests.conftest import TIMESERIES_SPEC

SNAPSHOT = Path(__file__).parent / "snapshots" / "grafana" / "timeseries.json"


def test_grafana_mapping_defaults() -> None:
    spec = registry.validate({**TIMESERIES_SPEC, "id": "fixed-id"})
    panel = registry.to_grafana(spec)

    assert panel["type"] == "timeseries"
    assert panel["title"] == "CPU idle"
    assert panel["fieldConfig"]["defaults"]["unit"] == "percentunit"
    assert panel["fieldConfig"]["defaults"]["custom"]["drawStyle"] == "line"
    assert panel["fieldConfig"]["defaults"]["custom"]["fillOpacity"] == 0
    assert panel["fieldConfig"]["defaults"]["custom"]["stacking"]["mode"] == "none"
    assert panel["options"]["legend"] == {
        "showLegend": True,
        "placement": "bottom",
        "displayMode": "list",
    }
    target = panel["targets"][0]
    assert target["refId"] == "A"
    assert target["legendFormat"] == "cpu {{cpu}}"
    assert target["range"] is True and target["instant"] is False
    assert "gridPos" not in panel  # placed by the exporter
    assert "timeFrom" not in panel


def test_grafana_mapping_options() -> None:
    spec = registry.validate(
        {
            **TIMESERIES_SPEC,
            "timeFrom": "24h",
            "options": {
                "draw": "bars",
                "stack": True,
                "fill": 1,
                "legend": "hidden",
                "min": 0,
                "max": 1,
            },
        }
    )
    panel = registry.to_grafana(spec)
    custom = panel["fieldConfig"]["defaults"]["custom"]
    assert custom["drawStyle"] == "bars"
    assert custom["stacking"]["mode"] == "normal"
    assert custom["fillOpacity"] == 100
    assert panel["fieldConfig"]["defaults"]["min"] == 0
    assert panel["fieldConfig"]["defaults"]["max"] == 1
    assert panel["options"]["legend"]["showLegend"] is False
    assert panel["timeFrom"] == "24h"


def test_grafana_snapshot() -> None:
    """Golden file: regenerate deliberately with UPDATE_SNAPSHOTS=1 when the mapping changes."""
    import os

    spec = registry.validate(
        {
            **TIMESERIES_SPEC,
            "id": "00000000-0000-0000-0000-000000000001",
            "description": "Idle CPU fraction per core",
            "queries": [
                {
                    "refId": "A",
                    "expr": "rate(node_cpu_seconds_total{mode='idle'}[5m])",
                    "legend": "{{cpu}}",
                },
                {
                    "refId": "B",
                    "expr": "count(node_cpu_seconds_total{mode='idle'})",
                    "instant": True,
                },
            ],
            "options": {"draw": "line", "fill": 0.25, "legend": "right"},
        }
    )
    panel = registry.to_grafana(spec)
    rendered = json.dumps(panel, indent=2, sort_keys=True) + "\n"

    if os.environ.get("UPDATE_SNAPSHOTS") or not SNAPSHOT.exists():
        SNAPSHOT.write_text(rendered)
    assert rendered == SNAPSHOT.read_text()
