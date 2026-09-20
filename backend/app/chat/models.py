from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.models import CamelModel


class ChatTurnRecord(CamelModel):
    """One message in a dashboard's transcript, in the shape the UI renders."""

    id: str
    seq: int
    role: Literal["user", "assistant"]
    content: str = ""
    reasoning: str = ""
    # Narration and tool steps in the order they happened; see the frontend's Block type.
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime


class ChatHistory(CamelModel):
    turns: list[ChatTurnRecord]
    # Highest seq in the whole transcript; clients poll with ?after=<seq>.
    last_seq: int
