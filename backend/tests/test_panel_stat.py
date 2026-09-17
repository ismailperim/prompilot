import json
import os
from pathlib import Path

import pytest

from app.panels import PanelValidationError, registry

SNAPSHOT = Path(__file__).parent / "snapshots" / "grafana" / "stat.json"

SPEC = {
    "type": "stat",
    "title": "Free disk",
    "queries": [{"refId": "A", "expr": "node_filesystem_avail_bytes{mountpoint='/'}"}],
    "unit": "bytes",
}


def test_defaults() -> None:
    spec = registry.validate(SPEC)
    assert spec.options == {
        "reduce": "last",
        "colorMode": "value",
        "graph": True,
        "decimals": None,
        "thresholds": [],
    }


def test_grafana_mapping_with_thresholds() -> None:
    spec = registry.validate(
        {
            **SPEC,
            "id": "00000000-0000-0000-0000-000000000003",
            "options": {
                "reduce": "mean",
                "colorMode": "background",
                "graph": False,
                "decimals": 1,
                "thresholds": [{"value": 90, "color": "red"}, {"value": 70, "color": "orange"}],
            },
        }
    )
    panel = registry.to_grafana(spec)
    assert panel["type"] == "stat"
    assert panel["options"]["reduceOptions"]["calcs"] == ["mean"]
    assert panel["options"]["colorMode"] == "background"
    assert panel["options"]["graphMode"] == "none"
    assert panel["fieldConfig"]["defaults"]["decimals"] == 1
    # sorted ascending, base step first
    assert panel["fieldConfig"]["defaults"]["thresholds"]["steps"] == [
        {"color": "green", "value": None},
        {"color": "orange", "value": 70},
        {"color": "red", "value": 90},
    ]


@pytest.mark.parametrize(
    "options",
    [
        {"reduce": "median"},
        {"thresholds": [{"value": 1, "color": "pink"}]},
        {"thresholds": [{"value": i, "color": "red"} for i in range(5)]},
        {"decimals": 9},
    ],
)
def test_invalid_options(options: dict) -> None:
    with pytest.raises(PanelValidationError):
        registry.validate({**SPEC, "options": options})


def test_snapshot() -> None:
    spec = registry.validate(
        {
            **SPEC,
            "id": "00000000-0000-0000-0000-000000000003",
            "options": {"thresholds": [{"value": 0.9, "color": "red"}]},
            "unit": "percentunit",
        }
    )
    rendered = json.dumps(registry.to_grafana(spec), indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_SNAPSHOTS") or not SNAPSHOT.exists():
        SNAPSHOT.write_text(rendered)
    assert rendered == SNAPSHOT.read_text()
