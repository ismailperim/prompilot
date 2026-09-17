import { Mic, Square } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useDashboard } from '../store/dashboard'
import { selectTurns, useChat } from './store'
import { canHear, canSpeak, hear, say, stopSaying, useVoice, type Hearing } from './voice'

/**
 * Hands-free conversation: press once, then talk. Each pause sends what you
 * said, the answer is read aloud, and it listens again — until pressed again.
 * Works with the side panel closed and in full screen.
 */
export function VoiceOrb() {
  const phase = useVoice((s) => s.phase)
  const level = useVoice((s) => s.level)
  const transcript = useVoice((s) => s.transcript)
  const error = useVoice((s) => s.error)
  const project = useDashboard((s) => s.project)
  const hearing = useRef<Hearing | null>(null)
  const running = useRef(false)

  useEffect(() => () => stop(), [])

  if (!project || !canHear()) return null

  function stop() {
    running.current = false
    hearing.current?.stop()
    hearing.current = null
    stopSaying()
    useChat.getState().stop()
    useVoice.setState({ phase: 'off', level: 0, transcript: '' })
  }

  async function start() {
    const voice = useVoice.getState()
    voice.setError(null)
    running.current = true
    const lang = navigator.language || 'en-US'
    let silentRounds = 0
    try {
      while (running.current) {
        voice.setPhase('listening')
        voice.setTranscript('')
        hearing.current = hear(lang, voice.setTranscript, voice.setLevel)
        const text = await hearing.current.text
        hearing.current = null
        if (!running.current) break
        if (!text) {
          // Nothing heard: give it a couple more chances, then stand down quietly.
          if (++silentRounds >= 3) break
          continue
        }
        silentRounds = 0
        voice.setTranscript(text)
        voice.setPhase('thinking')
        await useChat.getState().send(text)
        if (!running.current) break
        const turns = selectTurns(useChat.getState())
        const last = turns[turns.length - 1]
        const answer = last?.role === 'assistant' ? [...last.blocks].reverse().find((b) => b.kind === 'text') : null
        if (answer && answer.kind === 'text' && answer.text.trim() && canSpeak()) {
          voice.setPhase('speaking')
          await say(answer.text)
        }
      }
    } catch (e) {
      voice.setError(e instanceof Error ? e.message : String(e))
    } finally {
      stop()
    }
  }

  const label = { off: 'Talk to PromPilot', listening: 'Listening…', thinking: 'Thinking…', speaking: 'Speaking…' }[phase]
  const scale = phase === 'listening' ? 1 + Math.min(level * 12, 0.6) : 1

  return (
    <div className={`orb orb--${phase}`}>
      {(transcript || error) && phase !== 'off' && (
        <div className={`orb__bubble ${error ? 'orb__bubble--error' : ''}`}>{error ?? transcript}</div>
      )}
      <button
        className="orb__button"
        onClick={() => (phase === 'off' ? void start() : stop())}
        aria-label={phase === 'off' ? 'Start voice conversation' : 'Stop voice conversation'}
        aria-pressed={phase !== 'off'}
        title={label}
      >
        <span className="orb__ring" style={{ transform: `scale(${scale})` }} />
        {phase === 'off' ? <Mic size={18} /> : <Square size={16} />}
      </button>
      <span className="orb__label">{label}</span>
    </div>
  )
}
