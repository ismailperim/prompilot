"""Speech in and out. Which side does the work depends on STT_PROVIDER / TTS_PROVIDER."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import Field

from app.models import CamelModel
from app.voice.providers import VoiceError, VoiceServices

router = APIRouter(prefix="/api/voice", tags=["voice"])

MAX_AUDIO_BYTES = 10 * 1024 * 1024


def _voice(request: Request) -> VoiceServices:
    return request.app.state.voice


class VoiceCapabilities(CamelModel):
    stt: str  # browser | openai | gemini | elevenlabs
    tts: str  # browser | openai | elevenlabs


class TranscriptOut(CamelModel):
    text: str
    language: str | None = None


class SpeakIn(CamelModel):
    text: str = Field(min_length=1, max_length=4000)
    language: str | None = Field(default=None, max_length=16)


@router.get("", response_model=VoiceCapabilities)
async def capabilities(request: Request) -> VoiceCapabilities:
    """Tells the UI whether to use the browser's speech APIs or the server."""
    voice = _voice(request)
    return VoiceCapabilities(stt=voice.stt_provider, tts=voice.tts_provider)


@router.post("/transcribe", response_model=TranscriptOut)
async def transcribe(
    request: Request,
    file: Annotated[UploadFile, File()],
    language: Annotated[str | None, Form()] = None,
) -> TranscriptOut:
    voice = _voice(request)
    if voice.stt is None:
        raise HTTPException(status_code=503, detail="Server-side transcription is not configured")
    audio = await file.read(MAX_AUDIO_BYTES + 1)
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="audio is too large (max 10 MB)")
    if not audio:
        raise HTTPException(status_code=422, detail="empty audio")
    try:
        result = await voice.stt.transcribe(audio, file.content_type or "audio/wav", language)
    except VoiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TranscriptOut(text=result.text, language=result.language)


@router.post("/speak")
async def speak(request: Request, body: SpeakIn) -> Response:
    voice = _voice(request)
    if voice.tts is None:
        raise HTTPException(status_code=503, detail="Server-side speech is not configured")
    try:
        audio = await voice.tts.speak(body.text, body.language)
    except VoiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=audio, media_type=voice.tts.mime, headers={"Cache-Control": "no-store"})
