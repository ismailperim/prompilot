import httpx
from fastapi.testclient import TestClient

from tests.conftest import TIMESERIES_SPEC, P, json_response, load_fixture, mock_prometheus


def test_empty_dashboard(client: TestClient) -> None:
    body = client.get(f"{P}/dashboard").json()
    assert body["version"] == 1
    assert body["timeRange"] == {"from": "now-1h", "to": "now"}
    assert body["refresh"] == "30s"
    assert body["panels"] == []


def test_panel_crud_flow(client: TestClient) -> None:
    created = client.post(f"{P}/panels", json={"spec": TIMESERIES_SPEC})
    assert created.status_code == 201, created.text
    placement = created.json()
    panel_id = placement["spec"]["id"]
    assert placement["layout"] == {"x": 0, "y": 0, "w": 12, "h": 8}
    assert placement["spec"]["options"]["lineWidth"] == 1  # camelCase on the wire

    patched = client.patch(f"{P}/panels/{panel_id}", json={"options": {"draw": "bars"}})
    assert patched.status_code == 200
    assert patched.json()["spec"]["options"]["draw"] == "bars"

    replaced = client.put(f"{P}/panels/{panel_id}", json={**TIMESERIES_SPEC, "title": "Replaced"})
    assert replaced.status_code == 200
    assert replaced.json()["spec"]["title"] == "Replaced"
    assert replaced.json()["spec"]["options"]["draw"] == "line"

    layout = client.put(
        f"{P}/dashboard/layout",
        json=[{"id": panel_id, "layout": {"x": 0, "y": 0, "w": 24, "h": 6}}],
    )
    assert layout.json()["panels"][0]["layout"]["w"] == 24

    deleted = client.delete(f"{P}/panels/{panel_id}")
    assert deleted.status_code == 204
    assert client.delete(f"{P}/panels/{panel_id}").status_code == 404
    assert client.get(f"{P}/dashboard").json()["panels"] == []


def test_invalid_spec_returns_422_with_messages(client: TestClient) -> None:
    response = client.post(f"{P}/panels", json={"spec": {**TIMESERIES_SPEC, "type": "pie"}})
    assert response.status_code == 422
    assert "unknown panel type 'pie'" in response.json()["detail"][0]


def test_validate_endpoint_does_not_persist(client: TestClient) -> None:
    ok = client.post("/api/panels/validate", json=TIMESERIES_SPEC)
    assert ok.status_code == 200
    assert ok.json()["options"]["draw"] == "line"
    assert client.get(f"{P}/dashboard").json()["panels"] == []

    bad = client.post("/api/panels/validate", json={**TIMESERIES_SPEC, "unit": "x"})
    assert bad.status_code == 422


def test_dashboard_settings(client: TestClient) -> None:
    response = client.patch(
        f"{P}/dashboard", json={"title": "Prod", "timeRange": {"from": "now-6h", "to": "now"}}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Prod"
    assert response.json()["timeRange"]["from"] == "now-6h"

    response = client.patch(f"{P}/dashboard", json={"refresh": "10x"})
    assert response.status_code == 422


def test_panel_types_lists_schema(client: TestClient) -> None:
    types = client.get("/api/panels/types").json()
    assert [t["type"] for t in types] == ["stat", "table", "timeseries"]
    by_type = {t["type"]: t for t in types}
    assert "draw" in by_type["timeseries"]["optionsSchema"]["properties"]
    assert "thresholds" in by_type["stat"]["optionsSchema"]["properties"]


class TestData:
    @staticmethod
    def _prometheus(client: TestClient, calls: list[httpx.Request]) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if request.url.path == "/api/v1/query_range":
                return json_response(load_fixture("matrix"))
            if request.url.path == "/api/v1/query":
                return json_response(load_fixture("scalar"))
            return json_response(load_fixture("error_parse"), 400)

        mock_prometheus(client, handler)

    def test_batch_data_for_all_panels(self, client: TestClient) -> None:
        calls: list[httpx.Request] = []
        self._prometheus(client, calls)
        a = client.post(f"{P}/panels", json={"spec": TIMESERIES_SPEC}).json()["spec"]["id"]
        b = client.post(
            f"{P}/panels",
            json={
                "spec": {
                    **TIMESERIES_SPEC,
                    "queries": [{"refId": "A", "expr": "count(up)", "instant": True}],
                }
            },
        ).json()["spec"]["id"]

        response = client.post(f"{P}/panels/data", json={})
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body["panels"]) == {a, b}
        assert body["timeRange"]["to"] - body["timeRange"]["from"] == 3_600_000
        assert body["panels"][a]["error"] is None
        assert body["panels"][a]["frames"][0]["refId"] == "A"
        assert body["panels"][a]["frames"][0]["fields"][1]["name"] == "cpu 0"
        assert body["panels"][b]["frames"][0]["fields"][1]["values"] == [2.0]
        assert {c.url.path for c in calls} == {"/api/v1/query_range", "/api/v1/query"}

    def test_batch_data_with_ids_and_time_range(self, client: TestClient) -> None:
        calls: list[httpx.Request] = []
        self._prometheus(client, calls)
        a = client.post(f"{P}/panels", json={"spec": TIMESERIES_SPEC}).json()["spec"]["id"]
        client.post(f"{P}/panels", json={"spec": TIMESERIES_SPEC})

        response = client.post(
            f"{P}/panels/data", json={"ids": [a], "timeRange": {"from": "now-6h", "to": "now"}}
        )
        body = response.json()
        assert list(body["panels"]) == [a]
        assert body["timeRange"]["to"] - body["timeRange"]["from"] == 6 * 3_600_000
        assert len(calls) == 1
        # 6h / 1000 points → 21.6s → next nice step 30s
        assert calls[0].url.params["step"] == "30"

    def test_query_error_is_reported_per_panel(self, client: TestClient) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if "bad" in request.url.params.get("query", ""):
                return json_response(load_fixture("error_parse"), 400)
            return json_response(load_fixture("matrix"))

        mock_prometheus(client, handler)
        good = client.post(f"{P}/panels", json={"spec": TIMESERIES_SPEC}).json()["spec"]["id"]
        bad = client.post(
            f"{P}/panels",
            json={"spec": {**TIMESERIES_SPEC, "queries": [{"refId": "A", "expr": "rate(bad"}]}},
        ).json()["spec"]["id"]

        body = client.post(f"{P}/panels/data", json={}).json()
        assert body["panels"][good]["error"] is None
        assert "parse error" in body["panels"][bad]["error"]
        assert body["panels"][bad]["frames"] == []

    def test_single_panel_data_with_time_from_override(self, client: TestClient) -> None:
        calls: list[httpx.Request] = []
        self._prometheus(client, calls)
        panel_id = client.post(
            f"{P}/panels", json={"spec": {**TIMESERIES_SPEC, "timeFrom": "24h"}}
        ).json()["spec"]["id"]

        response = client.get(f"{P}/panels/{panel_id}/data")
        assert response.status_code == 200
        params = calls[0].url.params
        assert float(params["end"]) - float(params["start"]) == 86_400

    def test_single_panel_data_404(self, client: TestClient) -> None:
        assert client.get(f"{P}/panels/ghost/data").status_code == 404

    def test_bad_time_range_is_400(self, client: TestClient) -> None:
        response = client.post(
            f"{P}/panels/data", json={"timeRange": {"from": "yesterday", "to": "now"}}
        )
        assert response.status_code == 400
        assert "invalid time" in response.json()["detail"]

    def test_unreachable_prometheus_is_per_panel_error(self, client: TestClient) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        mock_prometheus(client, handler)
        panel_id = client.post(f"{P}/panels", json={"spec": TIMESERIES_SPEC}).json()["spec"]["id"]
        body = client.post(f"{P}/panels/data", json={}).json()
        assert "cannot reach Prometheus" in body["panels"][panel_id]["error"]
