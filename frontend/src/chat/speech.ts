/**
 * Voice in and out with the browser's own Web Speech API — no server, no keys.
 * Recognition is available in Chrome, Edge and Safari; synthesis nearly everywhere.
 */

type RecognitionCtor = new () => SpeechRecognitionLike

interface SpeechRecognitionLike {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null
  onend: (() => void) | null
  onerror: ((e: { error: string }) => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

function recognitionCtor(): RecognitionCtor | null {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export const speechInputSupported = () => recognitionCtor() !== null
export const speechOutputSupported = () => typeof window !== 'undefined' && 'speechSynthesis' in window

export interface Listener {
  stop: () => void
}

/** Start listening; `onText` receives the running transcript (interim + final). */
export function listen(
  lang: string,
  onText: (text: string, final: boolean) => void,
  onEnd: (error?: string) => void,
): Listener | null {
  const Ctor = recognitionCtor()
  if (!Ctor) return null
  const rec = new Ctor()
  rec.lang = lang
  rec.interimResults = true
  rec.continuous = false
  let finalText = ''
  rec.onresult = (e) => {
    let interim = ''
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i]
      if (r.isFinal) finalText += r[0].transcript
      else interim += r[0].transcript
    }
    onText((finalText + interim).trim(), interim === '' && finalText !== '')
  }
  rec.onerror = (e) => onEnd(e.error === 'no-speech' ? undefined : e.error)
  rec.onend = () => onEnd()
  rec.start()
  return { stop: () => rec.stop() }
}

/** Read text aloud in the given language, replacing anything currently being read. */
export function speak(text: string, lang: string): void {
  if (!speechOutputSupported()) return
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(stripMarkdown(text))
  utterance.lang = lang
  const voice = window.speechSynthesis.getVoices().find((v) => v.lang.toLowerCase().startsWith(lang.toLowerCase().slice(0, 2)))
  if (voice) utterance.voice = voice
  window.speechSynthesis.speak(utterance)
}

export function stopSpeaking(): void {
  if (speechOutputSupported()) window.speechSynthesis.cancel()
}

export function stripMarkdown(text: string): string {
  return text.replace(/\*\*([^*]+)\*\*/g, '$1').replace(/`([^`]+)`/g, '$1')
}

/** Guess the language of a short text: Turkish if it has Turkish-only letters or common words. */
export function guessLang(text: string, fallback = navigator.language || 'en-US'): string {
  if (/[çğışöüÇĞİŞÖÜ]/.test(text) || /\b(ve|bir|için|göster|ekle|panel|son)\b/i.test(text)) return 'tr-TR'
  if (/\b(the|show|add|and|for|last)\b/i.test(text)) return 'en-US'
  return fallback
}
