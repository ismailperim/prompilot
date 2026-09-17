"""STT/TTS providers.

Every provider speaks HTTP to something else; nothing here needs ffmpeg or
native audio libraries. The browser sends 16 kHz mono WAV, which every
backend below accepts.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings

ELEVENLABS_API = "https://api.elevenlabs.io/v1"


class VoiceError(Exception):
    """Provider failed; message is safe to show."""


@dataclass(slots=True)
class Transcript:
    text: str
    language: str | None = None


class SpeechToText(Protocol):
    name: str

    async def transcribe(self, audio: bytes, mime: str, language: str | None) -> Transcript: ...


class TextToSpeech(Protocol):
    name: str
    mime: str

    async def speak(self, text: str, language: str | None) -> bytes: ...


def _raise_for(response: httpx.Response, what: str) -> None:
    if response.status_code >= 400:
        detail = response.text[:300]
        raise VoiceError(f"{what} failed (HTTP {response.status_code}): {detail}")


# ---- STT --------------------------------------------------------------------


class OpenAISpeechToText:
    """``POST /audio/transcriptions`` — OpenAI, and local servers such as Speaches,
    faster-whisper-server or LocalAI."""

    name = "openai"

    def __init__(self, base_url: str, api_key: str | None, model: str, timeout: float) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._model = model

    async def transcribe(self, audio: bytes, mime: str, language: str | None) -> Transcript:
        data = {"model": self._model, "response_format": "json"}
        if language:
            data["language"] = language.split("-")[0]
        response = await self._client.post(
            "/audio/transcriptions",
            headers=self._headers,
            data=data,
            files={"file": ("audio.wav", audio, mime)},
        )
        _raise_for(response, "transcription")
        body = response.json()
        return Transcript(text=str(body.get("text", "")).strip(), language=body.get("language"))


class GeminiChatSpeechToText:
    """Audio in a chat completion (``input_audio``) — for gateways that expose Gemini
    through the OpenAI API but no transcription endpoint."""

    name = "gemini"

    def __init__(self, base_url: str, api_key: str | None, model: str, timeout: float) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._model = model

    async def transcribe(self, audio: bytes, mime: str, language: str | None) -> Transcript:
        fmt = "mp3" if "mp" in mime else "wav"
        hint = f" The speaker uses {language}." if language else ""
        payload = {
            "model": self._model,
            "max_tokens": 400,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Transcribe this audio exactly as spoken, in its original "
                            "language. Reply with the transcript only, no quotes, no commentary."
                            + hint,
                        },
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": base64.b64encode(audio).decode(),
                                "format": fmt,
                            },
                        },
                    ],
                }
            ],
        }
        response = await self._client.post("/chat/completions", headers=self._headers, json=payload)
        _raise_for(response, "transcription")
        content = response.json()["choices"][0]["message"].get("content") or ""
        return Transcript(text=content.strip().strip('"'), language=language)


class ElevenLabsSpeechToText:
    name = "elevenlabs"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        self._client = httpx.AsyncClient(base_url=ELEVENLABS_API, timeout=timeout)
        self._headers = {"xi-api-key": api_key}
        self._model = model

    async def transcribe(self, audio: bytes, mime: str, language: str | None) -> Transcript:
        data = {"model_id": self._model}
        if language:
            data["language_code"] = language.split("-")[0]
        response = await self._client.post(
            "/speech-to-text",
            headers=self._headers,
            data=data,
            files={"file": ("audio.wav", audio, mime)},
        )
        _raise_for(response, "transcription")
        body = response.json()
        return Transcript(
            text=str(body.get("text", "")).strip(), language=body.get("language_code")
        )


# ---- TTS --------------------------------------------------------------------


class OpenAITextToSpeech:
    """``POST /audio/speech`` — OpenAI, Kokoro-FastAPI, LocalAI, Speaches."""

    name = "openai"
    mime = "audio/mpeg"

    def __init__(
        self, base_url: str, api_key: str | None, model: str, voice: str, timeout: float
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._model = model
        self._voice = voice

    async def speak(self, text: str, language: str | None) -> bytes:
        response = await self._client.post(
            "/audio/speech",
            headers=self._headers,
            json={
                "model": self._model,
                "input": text,
                "voice": self._voice,
                "response_format": "mp3",
            },
        )
        _raise_for(response, "speech")
        return response.content


class ElevenLabsTextToSpeech:
    name = "elevenlabs"
    mime = "audio/mpeg"

    def __init__(self, api_key: str, model: str, voice: str, timeout: float) -> None:
        self._client = httpx.AsyncClient(base_url=ELEVENLABS_API, timeout=timeout)
        self._headers = {"xi-api-key": api_key}
        self._model = model
        self._voice = voice

    async def speak(self, text: str, language: str | None) -> bytes:
        payload: dict[str, object] = {"text": text, "model_id": self._model}
        if language:
            payload["language_code"] = language.split("-")[0]
        response = await self._client.post(
            f"/text-to-speech/{self._voice}",
            params={"output_format": "mp3_44100_128"},
            headers=self._headers,
            json=payload,
        )
        _raise_for(response, "speech")
        return response.content


# ---- factory ----------------------------------------------------------------


@dataclass(slots=True)
class VoiceServices:
    stt: SpeechToText | None
    tts: TextToSpeech | None
    stt_provider: str
    tts_provider: str


def build_voice(settings: Settings) -> VoiceServices:
    timeout = settings.voice_timeout.total_seconds()
    stt: SpeechToText | None = None
    tts: TextToSpeech | None = None

    if settings.stt_provider in ("openai", "gemini"):
        base = settings.stt_base_url or settings.llm_base_url
        key = settings.stt_api_key or settings.llm_api_key
        model = settings.stt_model or (
            "gemini-2.5-flash" if settings.stt_provider == "gemini" else "whisper-1"
        )
        if base:
            cls = (
                GeminiChatSpeechToText if settings.stt_provider == "gemini" else OpenAISpeechToText
            )
            stt = cls(base, key, model, timeout)
    elif settings.stt_provider == "elevenlabs":
        key = settings.stt_api_key or settings.elevenlabs_api_key
        if key:
            stt = ElevenLabsSpeechToText(key, settings.stt_model or "scribe_v1", timeout)

    if settings.tts_provider == "openai":
        base = settings.tts_base_url or settings.llm_base_url
        key = settings.tts_api_key or settings.llm_api_key
        if base:
            tts = OpenAITextToSpeech(
                base, key, settings.tts_model or "tts-1", settings.tts_voice or "alloy", timeout
            )
    elif settings.tts_provider == "elevenlabs":
        key = settings.tts_api_key or settings.elevenlabs_api_key
        if key:
            tts = ElevenLabsTextToSpeech(
                key,
                settings.tts_model or "eleven_flash_v2_5",
                settings.tts_voice or "21m00Tcm4TlvDq8ikWAM",  # "Rachel", ElevenLabs' default
                timeout,
            )

    return VoiceServices(
        stt=stt,
        tts=tts,
        stt_provider=settings.stt_provider
        if stt or settings.stt_provider == "browser"
        else "browser",
        tts_provider=settings.tts_provider
        if tts or settings.tts_provider == "browser"
        else "browser",
    )
