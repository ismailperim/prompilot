import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent.llm import AssistantTurn
from app.config import get_settings
from app.main import create_app
from tests.conftest import D, canned, json_response, load_fixture, mock_prometheus
from tests.test_agent import ScriptedProvider, call


def parse_sse(text: str) -> list[tuple[str, str]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], lines["data"]))
    return events


def test_chat_is_503_without_llm(client: TestClient) -> None:
    response = client.post(f"{D}/chat", json={"message": "hi"})
    assert response.status_code == 503
    assert "LLM_BASE_URL" in response.json()["detail"]


@pytest.fixture
def llm_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom.test:9090")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CATALOG_AUTOSTART", "false")
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_MODEL", "scripted")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()


def test_chat_streams_agent_events(llm_client: TestClient) -> None:
    mock_prometheus(llm_client, canned(json_response(load_fixture("matrix"))))
    llm_client.app.state.llm = ScriptedProvider(  # type: ignore[attr-defined]
        [
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
            AssistantTurn(content="Added the panel."),
        ]
    )

    with llm_client.stream(
        "POST", f"{D}/chat", json={"message": "add up", "history": []}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    events = parse_sse(body)
    names = [e for e, _ in events]
    assert names[0] == "turn"
    assert names[1] == "tool_call"
    assert "panel_added" in names
    assert names[-1] == "done"

    # Both turns are now in the shared transcript, in the shape the UI renders.
    history = llm_client.get(f"{D}/chat/history").json()
    assert [t["role"] for t in history["turns"]] == ["user", "assistant"]
    user, assistant = history["turns"]
    assert user["content"] == "add up"
    assert assistant["id"] == json.loads(events[0][1])["assistantId"]
    assert assistant["content"] == "Added the panel."
    kinds = [b["kind"] for b in assistant["blocks"]]
    assert kinds[0] == "step" and kinds[-1] == "text"
    step = assistant["blocks"][0]["step"]
    assert step["name"] == "emit_panel" and step["ok"] is True and step["summary"]
    assert history["lastSeq"] == assistant["seq"]
    assert '"Added the panel."' in body.replace(" \n", "\n") or "Added" in body
    assert len(llm_client.get(f"{D}").json()["panels"]) == 1


def test_chat_validates_request(llm_client: TestClient) -> None:
    assert llm_client.post(f"{D}/chat", json={"message": ""}).status_code == 422
    assert (
        llm_client.post(
            f"{D}/chat", json={"message": "x", "history": [{"role": "tool", "content": "y"}]}
        ).status_code
        == 422
    )


def test_stored_history_conditions_the_next_turn(llm_client: TestClient) -> None:
    mock_prometheus(llm_client, canned(json_response(load_fixture("matrix"))))
    first = ScriptedProvider([AssistantTurn(content="Sure, CPU it is.")])
    llm_client.app.state.llm = first  # type: ignore[attr-defined]
    llm_client.post(f"{D}/chat", json={"message": "cpu please"}).read()

    second = ScriptedProvider([AssistantTurn(content="Same for memory.")])
    llm_client.app.state.llm = second  # type: ignore[attr-defined]
    llm_client.post(f"{D}/chat", json={"message": "now memory"}).read()
    # the second request sent no history, yet the model saw the first exchange
    roles = [m["role"] for m in second.calls[0][0]]  # type: ignore[attr-defined]
    contents = [m.get("content") for m in second.calls[0][0]]  # type: ignore[attr-defined]
    assert "cpu please" in contents and "Sure, CPU it is." in contents
    assert roles[-1] == "user" and contents[-1] == "now memory"

    # ?after= returns only newer turns; DELETE wipes the transcript
    all_turns = llm_client.get(f"{D}/chat/history").json()
    assert len(all_turns["turns"]) == 4
    newer = llm_client.get(f"{D}/chat/history", params={"after": all_turns["turns"][1]["seq"]})
    assert [t["content"] for t in newer.json()["turns"]] == ["now memory", "Same for memory."]
    assert llm_client.delete(f"{D}/chat/history").status_code == 204
    assert llm_client.get(f"{D}/chat/history").json() == {"turns": [], "lastSeq": 0}
