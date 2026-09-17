# Voice

PromPilot can listen and talk. Where the speech work happens is a deployment
choice, so a homelab can stay fully local and a team can plug in a hosted
service — the UI is the same either way.

## In the UI

- **Microphone** in the composer: speak, pause, and what you said is sent.
- **Speaker** toggle: finished answers are read aloud.
- **Voice button** (bottom-right of the dashboard): a hands-free conversation.
  Press once, talk; each pause sends, the answer is spoken, and it listens
  again until you press it again. Works with the side panel closed and in
  full screen.

## Providers

| Setting | Values | Notes |
| --- | --- | --- |
| `STT_PROVIDER` | `browser` (default), `openai`, `gemini`, `elevenlabs` | Speech → text |
| `TTS_PROVIDER` | `browser` (default), `openai`, `elevenlabs` | Text → speech |

**browser** — the Web Speech API. Nothing to configure and nothing leaves the
browser except the transcript. Recognition works in Chrome, Edge and Safari
(not Firefox); synthesis works almost everywhere and uses the OS voices.

**openai** — the OpenAI audio API shape (`POST /audio/transcriptions`,
`POST /audio/speech`). Besides OpenAI itself this is what local servers speak:

- [Speaches](https://github.com/speaches-ai/speaches) / faster-whisper-server
  for transcription (`STT_MODEL=Systran/faster-whisper-small`).
- [Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) for speech
  (`TTS_MODEL=kokoro`, `TTS_VOICE=af_heart`).
- [LocalAI](https://localai.io) for both.

```
STT_PROVIDER=openai
STT_BASE_URL=http://speaches:8000/v1
STT_MODEL=Systran/faster-whisper-small
TTS_PROVIDER=openai
TTS_BASE_URL=http://kokoro:8880/v1
TTS_MODEL=kokoro
TTS_VOICE=af_heart
```

`STT_BASE_URL` / `STT_API_KEY` (and the TTS pair) default to `LLM_BASE_URL` /
`LLM_API_KEY`, so with OpenAI or a gateway that exposes Whisper and TTS you
only set the providers and models.

**gemini** — transcription through a chat completion with audio input, for
gateways that expose Gemini via the OpenAI API but no transcription endpoint.
`STT_MODEL` defaults to `gemini-2.5-flash`.

**elevenlabs** — `ELEVENLABS_API_KEY`, then `STT_PROVIDER=elevenlabs`
(Scribe, `STT_MODEL=scribe_v1`) and/or `TTS_PROVIDER=elevenlabs`
(`TTS_MODEL=eleven_flash_v2_5`, `TTS_VOICE=<voice id>`).

Audio leaves the browser as 16 kHz mono WAV, which every backend above
accepts; no ffmpeg is needed on the server. `GET /api/voice` tells the UI
which side does what.
