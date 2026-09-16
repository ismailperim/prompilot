import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.dashboard.models import Dashboard, Layout, PanelPlacement, TimeRange
from app.export.grafana import SCHEMA_VERSION, export_dashboard, slugify
from app.panels import registry
from tests.conftest import TIMESERIES_SPEC

SNAPSHOT = Path(__file__).parent / "snapshots" / "grafana" / "dashboard.json"


def _dashboard() -> Dashboard:
    cpu = registry.validate({**TIMESERIES_SPEC, "id": "00000000-0000-0000-0000-000000000001"})
    mem = registry.validate(
        {
            **TIMESERIES_SPEC,
            "id": "00000000-0000-0000-0000-000000000002",
            "title": "Memory",
            "unit": "bytes",
            "queries": [{"refId": "A", "expr": "node_memory_MemAvailable_bytes"}],
            "options": {"fill": 0.2, "legend": "right"},
        }
    )
    return Dashboard(
        title="Node overview",
        time_range=TimeRange(from_="now-6h", to="now"),
        refresh="1m",
        panels=[
            # Deliberately out of visual order: export sorts by (y, x).
            PanelPlacement(spec=mem, layout=Layout(x=12, y=0, w=12, h=8)),
            PanelPlacement(spec=cpu, layout=Layout(x=0, y=0, w=12, h=8)),
        ],
    )


def test_export_structure() -> None:
    doc = export_dashboard(_dashboard())

    assert doc["schemaVersion"] == SCHEMA_VERSION
    assert doc["title"] == "Node overview"
    assert doc["time"] == {"from": "now-6h", "to": "now"}
    assert doc["refresh"] == "1m"
    assert doc["uid"] is None and doc["id"] is None  # Grafana assigns on import
    assert doc["__inputs"][0]["name"] == "DS_PROMETHEUS"
    assert {r["id"] for r in doc["__requires"]} == {"grafana", "prometheus", "timeseries"}

    panels = doc["panels"]
    assert [p["title"] for p in panels] == ["CPU idle", "Memory"]
    assert [p["id"] for p in panels] == [1, 2]
    assert panels[0]["gridPos"] == {"x": 0, "y": 0, "w": 12, "h": 8}
    assert panels[1]["gridPos"] == {"x": 12, "y": 0, "w": 12, "h": 8}
    assert panels[0]["datasource"] == {"type": "prometheus", "uid": "${DS_PROMETHEUS}"}
    assert panels[0]["targets"][0]["datasource"]["uid"] == "${DS_PROMETHEUS}"


def test_refresh_off_exports_empty_string() -> None:
    dashboard = _dashboard()
    dashboard.refresh = None
    assert export_dashboard(dashboard)["refresh"] == ""


def test_export_snapshot() -> None:
    rendered = json.dumps(export_dashboard(_dashboard()), indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_SNAPSHOTS") or not SNAPSHOT.exists():
        SNAPSHOT.write_text(rendered)
    assert rendered == SNAPSHOT.read_text()


def test_slugify() -> None:
    assert slugify("Node overview (prod) #1") == "node-overview-prod-1"
    assert slugify("///") == "dashboard"


def test_export_endpoint_downloads_json(client: TestClient) -> None:
    client.patch("/api/dashboard", json={"title": "My Board"})
    client.post("/api/panels", json={"spec": TIMESERIES_SPEC})

    response = client.get("/api/export/grafana")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"] == 'attachment; filename="my-board.grafana.json"'
    doc = response.json()
    assert doc["title"] == "My Board"
    assert len(doc["panels"]) == 1

    inline = client.get("/api/export/grafana", params={"download": "false"})
    assert "content-disposition" not in inline.headers
