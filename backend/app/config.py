"""Application settings, loaded from environment variables."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DURATION_RE = re.compile(r"^(\d+)(ms|s|m|h|d|w)$")
_DURATION_UNITS = {
    "ms": timedelta(milliseconds=1),
    "s": timedelta(seconds=1),
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
}


def parse_duration(value: str | timedelta) -> timedelta:
    """Parse Prometheus-style durations such as ``30s``, ``5m``, ``24h``, ``2w``."""
    if isinstance(value, timedelta):
        return value
    match = _DURATION_RE.match(value.strip())
    if not match:
        raise ValueError(f"invalid duration {value!r}; expected e.g. 30s, 5m, 24h")
    amount, unit = match.groups()
    return int(amount) * _DURATION_UNITS[unit]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Prometheus
    prometheus_url: str = Field(default="http://localhost:9090")
    prometheus_username: str | None = None
    prometheus_password: str | None = None
    prometheus_query_timeout: timedelta = timedelta(seconds=30)
    prometheus_max_data_points: int = 1000

    # LLM (optional). Chat is disabled when base URL is empty.
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_timeout: timedelta = timedelta(seconds=120)
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.2
    # Extra JSON merged into every chat completion request, for vendor-specific knobs.
    # e.g. '{"chat_template_kwargs": {"enable_thinking": false}}' turns off Qwen thinking on vLLM.
    # Kept as text so an empty value from a compose file is simply "no extras".
    llm_extra_body: str | None = None
    llm_max_tool_iterations: int = 8
    llm_history_turns: int = 10  # user/assistant pairs re-sent from the client

    # Catalog
    catalog_llm_enrich: bool = False
    catalog_rebuild_interval: timedelta = timedelta(hours=24)
    catalog_label_sample_limit: int = 2000  # max metrics whose label keys are sampled per build
    catalog_concurrency: int = 6  # parallel Prometheus calls during a build
    catalog_autostart: bool = True  # build on startup; tests turn this off

    # Authentication (see docs/auth.md). Unset AUTH_PASSWORD = open instance.
    auth_password: str | None = None
    auth_api_token: str | None = None  # for scripts: Authorization: Bearer <token>
    auth_session_ttl: timedelta = timedelta(days=30)
    auth_cookie_secure: bool = False  # set true behind HTTPS
    secret_key: str | None = (
        None  # signs sessions, encrypts stored passwords; auto-generated when unset
    )

    # Voice (see docs/voice.md). "browser" = Web Speech API in the browser, no server work.
    stt_provider: Literal["browser", "openai", "gemini", "elevenlabs"] = "browser"
    stt_base_url: str | None = None  # openai/gemini: defaults to LLM_BASE_URL
    stt_api_key: str | None = None  # defaults to LLM_API_KEY (or ELEVENLABS_API_KEY)
    stt_model: str | None = (
        None  # e.g. whisper-1, Systran/faster-whisper-small, gemini-2.5-flash, scribe_v1
    )
    tts_provider: Literal["browser", "openai", "elevenlabs"] = "browser"
    tts_base_url: str | None = None
    tts_api_key: str | None = None
    tts_model: str | None = None  # e.g. tts-1, kokoro, eleven_flash_v2_5
    tts_voice: str | None = None  # e.g. alloy, af_heart, or an ElevenLabs voice id
    elevenlabs_api_key: str | None = None
    voice_timeout: timedelta = timedelta(seconds=60)

    # Knowledge base: Markdown files describing the target system (see docs/knowledge.md)
    knowledge_dir: Path | None = None  # default: <DATA_DIR>/knowledge

    # Runtime
    data_dir: Path = Path("/data")
    port: int = 8080
    log_level: str = "info"

    @field_validator("llm_extra_body", mode="after")
    @classmethod
    def _check_json_object(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("LLM_EXTRA_BODY must be a JSON object")
        return value

    @property
    def llm_extra_body_json(self) -> dict[str, Any]:
        return json.loads(self.llm_extra_body) if self.llm_extra_body else {}

    @field_validator(
        "prometheus_username",
        "prometheus_password",
        "llm_base_url",
        "llm_model",
        "llm_api_key",
        "stt_base_url",
        "stt_api_key",
        "stt_model",
        "tts_base_url",
        "tts_api_key",
        "tts_model",
        "tts_voice",
        "elevenlabs_api_key",
        "auth_password",
        "auth_api_token",
        "secret_key",
        mode="before",
    )
    @classmethod
    def _empty_string_is_none(cls, value: object) -> object:
        """``LLM_MODEL=`` in a compose file means "not set", not "the empty model"."""
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator(
        "prometheus_query_timeout",
        "llm_timeout",
        "catalog_rebuild_interval",
        "voice_timeout",
        "auth_session_ttl",
        mode="before",
    )
    @classmethod
    def _parse_durations(cls, value: object) -> object:
        if isinstance(value, str):
            if value.strip() == "0":
                return timedelta(0)
            return parse_duration(value)
        return value

    @property
    def knowledge_path(self) -> Path:
        return self.knowledge_dir or self.data_dir / "knowledge"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_base_url and self.llm_model)


@lru_cache
def get_settings() -> Settings:
    return Settings()
