"""Turns the agent's event stream into the transcript blocks the UI renders."""

from __future__ import annotations

import time
from typing import Any

from app.agent.loop import AgentEvent

# Tool results can carry query samples; beyond this they are dropped from the transcript
# (the summary line stays), the live client already showed them.
MAX_RESULT_CHARS = 20_000


class TurnRecorder:
    """Feed it every event of one assistant turn; read ``content``/``reasoning``/``blocks``."""

    def __init__(self) -> None:
        self.content = ""
        self.reasoning = ""
        self.blocks: list[dict[str, Any]] = []
        self.error: str | None = None

    def observe(self, event: AgentEvent) -> None:
        data = event.data
        match event.type:
            case "text_delta":
                text = str(data.get("text", ""))
                self.content += text
                last = self.blocks[-1] if self.blocks else None
                if last is not None and last["kind"] == "text":
                    last["text"] += text
                else:
                    self.blocks.append({"kind": "text", "text": text})
            case "reasoning_delta":
                self.reasoning += str(data.get("text", ""))
            case "tool_call":
                self.blocks.append(
                    {
                        "kind": "step",
                        "step": {
                            "id": data.get("id"),
                            "name": data.get("name"),
                            "arguments": data.get("arguments"),
                            "startedAt": _now_ms(),
                        },
                    }
                )
            case "tool_result":
                for block in reversed(self.blocks):
                    if block["kind"] == "step" and block["step"]["id"] == data.get("id"):
                        result = data.get("result")
                        if result is not None and len(str(result)) > MAX_RESULT_CHARS:
                            result = None
                        block["step"].update(
                            ok=bool(data.get("ok")),
                            summary=str(data.get("summary", "")),
                            result=result,
                            finishedAt=_now_ms(),
                        )
                        break
            case "error":
                self.error = str(data.get("message") or "Unknown error")


def _now_ms() -> int:
    return int(time.time() * 1000)
