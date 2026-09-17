import re

from fastapi.testclient import TestClient

from app.agent.llm import AssistantTurn
from tests.conftest import TIMESERIES_SPEC, D, canned, json_response, load_fixture, mock_prometheus
from tests.test_agent import ScriptedProvider, call


def value(body: str, line_start: str) -> float:
    """Value of the sample whose line starts with ``line_start``; 0 when absent."""
    for line in body.splitlines():
        if line.startswith(line_start + " "):
            return float(line.split(" ")[-1])
    return 0.0


def test_metrics_endpoint_exposes_http_and_project_metrics(client: TestClient) -> None:
    client.get("/api/projects")
    client.get("/api/projects/nope/status")
    body = client.get("/metrics").text
    assert "prompilot_http_requests_total" in body
    assert 'route="/api/projects",status="200"' in body
    assert 'route="/api/projects/{slug}/status",status="404"' in body
    assert "prompilot_projects 1.0" in body
    assert "prompilot_http_request_duration_seconds_bucket" in body


def test_metrics_endpoint_is_open_and_not_self_counted(client: TestClient) -> None:
    before = client.get("/metrics").text
    after = client.get("/metrics").text
    assert 'route="/metrics"' not in after
    assert "prompilot_http_requests_total" in before


def test_chat_and_tool_metrics(client: TestClient) -> None:
    before = client.get("/metrics").text
    mock_prometheus(client, canned(json_response(load_fixture("matrix"))))
    client.app.state.llm = ScriptedProvider(  # type: ignore[attr-defined]
        [
            AssistantTurn(tool_calls=[call("search_catalog", query="cpu")]),
            AssistantTurn(
                tool_calls=[
                    call(
                        "emit_panel",
                        type="timeseries",
                        title="Up",
                        queries=[{"expr": "up"}],
                        unit="short",
                    )
                ]
            ),
            AssistantTurn(content="done"),
        ]
    )
    with client.stream("POST", f"{D}/chat", json={"message": "add up"}) as response:
        list(response.iter_text())
    after = client.get("/metrics").text
    delta = lambda key: value(after, key) - value(before, key)  # noqa: E731
    assert delta('prompilot_chat_requests_total{outcome="answered"}') == 1
    assert delta('prompilot_tool_calls_total{ok="true",tool="search_catalog"}') == 1
    assert delta('prompilot_tool_calls_total{ok="true",tool="emit_panel"}') == 1
    assert delta("prompilot_llm_turns_per_chat_count") == 1
    assert delta("prompilot_llm_turn_duration_seconds_count") == 3
    assert delta('prompilot_tool_call_duration_seconds_count{tool="emit_panel"}') == 1
    assert re.search(r"prompilot_chat_duration_seconds_sum \d", after)
    assert TIMESERIES_SPEC["type"] == "timeseries"
