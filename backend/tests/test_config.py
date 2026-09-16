from datetime import timedelta

import pytest

from app.config import Settings, parse_duration


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("500ms", timedelta(milliseconds=500)),
        ("30s", timedelta(seconds=30)),
        ("5m", timedelta(minutes=5)),
        ("24h", timedelta(hours=24)),
        ("2d", timedelta(days=2)),
    ],
)
def test_parse_duration(raw: str, expected: timedelta) -> None:
    assert parse_duration(raw) == expected


@pytest.mark.parametrize("raw", ["", "30", "30x", "-5s", "1.5h"])
def test_parse_duration_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_duration(raw)


def test_settings_parse_durations_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMETHEUS_QUERY_TIMEOUT", "10s")
    monkeypatch.setenv("CATALOG_REBUILD_INTERVAL", "0")
    settings = Settings(_env_file=None)
    assert settings.prometheus_query_timeout == timedelta(seconds=10)
    assert settings.catalog_rebuild_interval == timedelta(0)


def test_llm_enabled_requires_url_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings(_env_file=None).llm_enabled is False
    monkeypatch.setenv("LLM_BASE_URL", "http://ollama:11434/v1")
    assert Settings(_env_file=None).llm_enabled is False
    monkeypatch.setenv("LLM_MODEL", "llama3.1")
    assert Settings(_env_file=None).llm_enabled is True


def test_empty_optional_strings_become_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "")
    monkeypatch.setenv("LLM_BASE_URL", "   ")
    monkeypatch.setenv("PROMETHEUS_USERNAME", "")
    settings = Settings(_env_file=None)
    assert settings.llm_model is None
    assert settings.llm_base_url is None
    assert settings.prometheus_username is None
    assert settings.llm_enabled is False
