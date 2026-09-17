import json
import os
from pathlib import Path

import pytest

from app.panels import PanelValidationError, registry

SNAPSHOT = Path(__file__).parent / "snapshots" / "grafana" / "gauge.json"

SPEC = {
    "type": "gauge",
    "title": "Memory used",
    "queries": [
        {"refId": "A", "expr": "1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes"}
    ],
    "unit": "percentunit",
}


def test_defaults() -> None:
    spec = registry.validate(SPEC)
    assert spec.options == {
        "min": 0,
        "max": 1,
        "reduce": "last",
        "decimals": None,
        "thresholds": [],
        "showThresholdMarkers": True,
    }


def test_grafana_mapping() -> None:
    spec = registry.validate(
        {
            **SPEC,
            "id": "00000000-0000-0000-0000-000000000005",
            "options": {
                "min": 0,
                "max": 100,
                "reduce": "mean",
                "decimals": 0,
                "thresholds": [{"value": 90, "color": "red"}, {"value": 70, "color": "orange"}],
                "showThresholdMarkers": False,
            },
        }
    )
    panel = registry.to_grafana(spec)
    assert panel["type"] == "gauge"
    defaults = panel["fieldConfig"]["defaults"]
    assert (defaults["min"], defaults["max"], defaults["decimals"]) == (0, 100, 0)
    assert [s["color"] for s in defaults["thresholds"]["steps"]] == ["green", "orange", "red"]
    assert panel["options"]["reduceOptions"]["calcs"] == ["mean"]
    assert panel["options"]["showThresholdMarkers"] is False


@pytest.mark.parametrize(
    "options",
    [
        {"max": 0},
        {"min": 5, "max": 5},
        {"reduce": "median"},
        {"thresholds": [{"value": 1, "color": "pink"}]},
    ],
)
def test_invalid_options(options: dict) -> None:
    with pytest.raises(PanelValidationError):
        registry.validate({**SPEC, "options": options})


def test_snapshot() -> None:
    spec = registry.validate(
        {
            **SPEC,
            "id": "00000000-0000-0000-0000-000000000005",
            "options": {
                "thresholds": [{"value": 0.7, "color": "orange"}, {"value": 0.9, "color": "red"}]
            },
        }
    )
    rendered = json.dumps(registry.to_grafana(spec), indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_SNAPSHOTS") or not SNAPSHOT.exists():
        SNAPSHOT.write_text(rendered)
    assert rendered == SNAPSHOT.read_text()
