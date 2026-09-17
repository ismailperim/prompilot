import json
import os
from pathlib import Path

import pytest

from app.panels import PanelValidationError, registry

SNAPSHOT = Path(__file__).parent / "snapshots" / "grafana" / "table.json"

SPEC = {
    "type": "table",
    "title": "Disk usage per mountpoint",
    "queries": [
        {
            "refId": "A",
            "expr": "1 - node_filesystem_avail_bytes / node_filesystem_size_bytes",
            "instant": True,
        }
    ],
    "unit": "percentunit",
}


def test_defaults() -> None:
    spec = registry.validate(SPEC)
    assert spec.options == {
        "sortBy": None,
        "sortDesc": True,
        "limit": 100,
        "hideColumns": [],
        "valueColumn": "Value",
    }


def test_grafana_mapping_forces_instant_table_targets() -> None:
    spec = registry.validate(
        {
            **SPEC,
            "queries": [{"refId": "A", "expr": "up"}],  # not instant in the spec
            "options": {
                "sortBy": "value",
                "limit": 10,
                "hideColumns": ["job"],
                "valueColumn": "Used",
            },
        }
    )
    panel = registry.to_grafana(spec)
    assert panel["type"] == "table"
    target = panel["targets"][0]
    assert target["instant"] is True and target["range"] is False and target["format"] == "table"
    ids = [t["id"] for t in panel["transformations"]]
    assert ids == ["organize", "sortBy", "limit"]
    organize = panel["transformations"][0]["options"]
    assert organize["excludeByName"] == {"Time": True, "__name__": True, "job": True}
    assert organize["renameByName"] == {"Value": "Used"}
    assert panel["transformations"][1]["options"]["sort"] == [{"field": "Used", "desc": True}]
    assert panel["transformations"][2]["options"]["limitField"] == 10


@pytest.mark.parametrize("options", [{"limit": 0}, {"limit": 5000}, {"hideColumns": "job"}])
def test_invalid_options(options: dict) -> None:
    with pytest.raises(PanelValidationError):
        registry.validate({**SPEC, "options": options})


def test_snapshot() -> None:
    spec = registry.validate(
        {
            **SPEC,
            "id": "00000000-0000-0000-0000-000000000004",
            "options": {"sortBy": "value", "limit": 20, "hideColumns": ["job", "instance"]},
        }
    )
    rendered = json.dumps(registry.to_grafana(spec), indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_SNAPSHOTS") or not SNAPSHOT.exists():
        SNAPSHOT.write_text(rendered)
    assert rendered == SNAPSHOT.read_text()
