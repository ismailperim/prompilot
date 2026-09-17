/**
 * One place that knows how to hear and speak, whichever side does the work:
 * the server (`/api/voice`, when STT/TTS providers are configured) or the
 * browser's own Web Speech API.
 */

import { create } from 'zustand'
import { record, type ActiveRecorder } from './recorder'
import { guessLang, listen, speak as browserSpeak, speechInputSupported, speechOutputSupported, stopSpeaking as browserStop, type Listener } from './speech'

export interface VoiceCapabilities {
  stt: 'browser' | 'openai' | 'gemini' | 'elevenlabs'
  tts: 'browser' | 'openai' | 'elevenlabs'
}

let capabilities: VoiceCapabilities = { stt: 'browser', tts: 'browser' }

export async function loadVoiceCapabilities(): Promise<VoiceCapabilities> {
  try {
    const response = await fetch('/api/voice')
    if (response.ok) capabilities = (await response.json()) as VoiceCapabilities
  } catch {
    /* keep browser defaults */
  }
  return capabilities
}

export const canHear = () => capabilities.stt !== 'browser' || speechInputSupported()
export const canSpeak = () => capabilities.tts !== 'browser' || speechOutputSupported()

// ---- hearing ---------------------------------------------------------------

export interface Hearing {
  stop: () => void
  /** Resolves with the transcript ('' when nothing was said). */
  text: Promise<string>
}

/** Listen for one utterance. `onInterim` only fires with the browser recognizer. */
export function hear(lang: string, onInterim?: (text: string) => void, onLevel?: (rms: number) => void): Hearing {
  if (capabilities.stt === 'browser') {
    let resolveText!: (t: string) => void
    const text = new Promise<string>((resolve) => {
      resolveText = resolve
    })
    let finalText = ''
    const listener: Listener | null = listen(
      lang,
      (t, final) => {
        onInterim?.(t)
        if (final) finalText = t
      },
      () => resolveText(finalText.trim()),
    )
    if (!listener) resolveText('')
    return { stop: () => listener?.stop(), text }
  }

  let active: ActiveRecorder | null = null
  const text = (async () => {
    active = await record({ onLevel })
    const recording = await active.done
    if (!recording.hadSpeech || recording.durationMs < 400) return ''
    const form = new FormData()
    form.append('file', recording.blob, 'speech.wav')
    form.append('language', lang)
    const response = await fetch('/api/voice/transcribe', { method: 'POST', body: form })
    if (!response.ok) {
      const detail = await response.json().then((b: { detail?: string }) => b.detail).catch(() => null)
      throw new Error(detail ?? `Transcription failed (${response.status})`)
    }
    const body = (await response.json()) as { text: string }
    return body.text.trim()
  })()
  return { stop: () => active?.stop(), text }
}

// ---- speaking --------------------------------------------------------------

let audio: HTMLAudioElement | null = null

/** Read text aloud; resolves when playback ends (or immediately if it cannot start). */
export async function say(text: string, lang = guessLang(text)): Promise<void> {
  stopSaying()
  if (capabilities.tts === 'browser') {
    if (!speechOutputSupported()) return
    return new Promise((resolve) => {
      browserSpeak(text, lang)
      const poll = window.setInterval(() => {
        if (!window.speechSynthesis.speaking) {
          window.clearInterval(poll)
          resolve()
        }
      }, 200)
    })
  }
  const response = await fetch('/api/voice/speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: text.slice(0, 4000), language: lang }),
  })
  if (!response.ok) return
  const url = URL.createObjectURL(await response.blob())
  return new Promise((resolve) => {
    audio = new Audio(url)
    audio.onended = audio.onerror = () => {
      URL.revokeObjectURL(url)
      resolve()
    }
    void audio.play().catch(() => resolve())
  })
}

export function stopSaying(): void {
  browserStop()
  if (audio) {
    audio.pause()
    audio = null
  }
}

// ---- voice session state (the orb) ----------------------------------------

export type VoicePhase = 'off' | 'listening' | 'thinking' | 'speaking'

interface VoiceState {
  phase: VoicePhase
  level: number
  transcript: string
  error: string | null
  setPhase: (phase: VoicePhase) => void
  setLevel: (level: number) => void
  setTranscript: (text: string) => void
  setError: (error: string | null) => void
}

export const useVoice = create<VoiceState>((set) => ({
  phase: 'off',
  level: 0,
  transcript: '',
  error: null,
  setPhase: (phase) => set({ phase }),
  setLevel: (level) => set({ level }),
  setTranscript: (transcript) => set({ transcript }),
  setError: (error) => set({ error }),
}))
