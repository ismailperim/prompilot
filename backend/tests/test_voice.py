from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.voice.providers import (
    ElevenLabsTextToSpeech,
    GeminiChatSpeechToText,
    OpenAISpeechToText,
    OpenAITextToSpeech,
    VoiceError,
    build_voice,
)

WAV = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 24


def _mock(provider: object, handler) -> None:  # type: ignore[no-untyped-def]
    client: httpx.AsyncClient = provider._client  # type: ignore[attr-defined]
    provider._client = httpx.AsyncClient(  # type: ignore[attr-defined]
        base_url=client.base_url, transport=httpx.MockTransport(handler)
    )


async def test_openai_stt_posts_multipart_with_language() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.content
        return httpx.Response(200, json={"text": " show cpu ", "language": "en"})

    stt = OpenAISpeechToText("http://stt.local/v1", "k", "whisper-1", 10)
    _mock(stt, handler)
    out = await stt.transcribe(WAV, "audio/wav", "en-US")
    assert out.text == "show cpu" and out.language == "en"
    assert seen["path"] == "/v1/audio/transcriptions" and seen["auth"] == "Bearer k"
    body = seen["body"]
    assert isinstance(body, bytes) and b'name="language"' in body and b"whisper-1" in body


async def test_gemini_stt_sends_input_audio() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": '"Merhaba dünya"'}}]})

    stt = GeminiChatSpeechToText("http://gw/v1", None, "gemini-2.5-flash", 10)
    _mock(stt, handler)
    out = await stt.transcribe(WAV, "audio/wav", "tr-TR")
    assert out.text == "Merhaba dünya"
    payload = seen["json"]
    assert isinstance(payload, dict) and payload["model"] == "gemini-2.5-flash"
    parts = payload["messages"][0]["content"]
    assert parts[1]["type"] == "input_audio" and parts[1]["input_audio"]["format"] == "wav"


async def test_openai_tts_returns_bytes_and_errors_are_typed() -> None:
    tts = OpenAITextToSpeech("http://tts.local/v1", None, "kokoro", "af_heart", 10)
    _mock(
        tts,
        lambda r: httpx.Response(200, content=b"ID3mp3", headers={"content-type": "audio/mpeg"}),
    )
    assert await tts.speak("hi", "en") == b"ID3mp3"

    _mock(tts, lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(VoiceError, match="HTTP 500"):
        await tts.speak("hi", "en")


async def test_elevenlabs_tts_uses_voice_and_key() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["key"] = request.headers.get("xi-api-key")
        return httpx.Response(200, content=b"mp3")

    tts = ElevenLabsTextToSpeech("xi", "eleven_flash_v2_5", "voice123", 10)
    _mock(tts, handler)
    assert await tts.speak("hello", "en-US") == b"mp3"
    assert seen["path"] == "/v1/text-to-speech/voice123" and seen["key"] == "xi"


def test_build_voice_defaults_to_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    voice = build_voice(Settings(_env_file=None))
    assert voice.stt is None and voice.tts is None
    assert (voice.stt_provider, voice.tts_provider) == ("browser", "browser")

    monkeypatch.setenv("STT_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_BASE_URL", "http://gw/v1")
    monkeypatch.setenv("TTS_PROVIDER", "elevenlabs")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "xi")
    voice = build_voice(Settings(_env_file=None))
    assert isinstance(voice.stt, GeminiChatSpeechToText) and isinstance(
        voice.tts, ElevenLabsTextToSpeech
    )

    # provider requested but nothing to build it from → falls back to the browser
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    voice = build_voice(Settings(_env_file=None))
    assert voice.tts is None and voice.tts_provider == "browser"


@pytest.fixture
def vclient(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom.test:9090")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CATALOG_AUTOSTART", "false")
    monkeypatch.setenv("STT_PROVIDER", "openai")
    monkeypatch.setenv("STT_BASE_URL", "http://stt.local/v1")
    monkeypatch.setenv("STT_MODEL", "whisper-1")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            yield client
    finally:
        get_settings.cache_clear()


def test_voice_endpoints(vclient: TestClient) -> None:
    assert vclient.get("/api/voice").json() == {"stt": "openai", "tts": "browser"}

    stt = vclient.app.state.voice.stt  # type: ignore[attr-defined]
    _mock(stt, lambda r: httpx.Response(200, json={"text": "disk usage", "language": "en"}))
    response = vclient.post(
        "/api/voice/transcribe",
        files={"file": ("a.wav", WAV, "audio/wav")},
        data={"language": "en-US"},
    )
    assert response.status_code == 200 and response.json() == {
        "text": "disk usage",
        "language": "en",
    }

    assert vclient.post("/api/voice/speak", json={"text": "hi"}).status_code == 503
    empty = vclient.post("/api/voice/transcribe", files={"file": ("a.wav", b"", "audio/wav")})
    assert empty.status_code == 422
