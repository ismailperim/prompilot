import { AlertTriangle, ArrowUp, Check, Eraser, Mic, MicOff, Play, Square, Volume2, VolumeX } from 'lucide-react'
import { Fragment, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { currentApi, useDashboard } from '../store/dashboard'
import type { KnowledgeStatus } from '../api/types'
import type { SystemStatus } from '../api/types'
import { useLayout, VOICE_LANGUAGES } from '../theme'
import { Markdown } from './Markdown'
import { canHear, canSpeak, hear, say, stopSaying, type Hearing } from './voice'
import { describeStep, selectTurns, useChat, type Block, type ChatTurn, type ToolStep } from './store'

const SUGGESTIONS = [
  'Show CPU usage per core as a percentage',
  'Memory available over time',
  'Network throughput per interface, received and transmitted',
  'How long do Prometheus scrapes take?',
]

const POLL_MS = 15_000

export function ChatPanel({ status }: { status: SystemStatus | null }) {
  const project = useDashboard((s) => s.project)
  const dashboardId = useDashboard((s) => s.dashboardId)
  const conversations = useChat((s) => s.conversations)
  const turns = useChat(selectTurns)
  const sending = useChat((s) => s.sending)
  const send = useChat((s) => s.send)
  const stop = useChat((s) => s.stop)
  const clear = useChat((s) => s.clear)
  const [draft, setDraft] = useState('')
  const [knowledge, setKnowledge] = useState<KnowledgeStatus | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const voiceReplies = useLayout((s) => s.voiceReplies)
  const setVoiceReplies = useLayout((s) => s.setVoiceReplies)
  const voiceLang = useLayout((s) => s.voiceLang)
  const setVoiceLang = useLayout((s) => s.setVoiceLang)
  const [listening, setListening] = useState(false)
  const listener = useRef<Hearing | null>(null)
  const spoken = useRef(new Set<string>())

  // Read each finished answer aloud once, if voice replies are on.
  useEffect(() => {
    if (!voiceReplies) return
    const last = turns[turns.length - 1]
    if (!last || last.role !== 'assistant' || last.pending || spoken.current.has(last.id)) return
    spoken.current.add(last.id)
    const text = [...last.blocks].reverse().find((b) => b.kind === 'text')
    if (text && text.kind === 'text' && text.text.trim()) void say(text.text)
  }, [turns, voiceReplies])

  const toggleListening = () => {
    if (listening) {
      listener.current?.stop()
      return
    }
    stopSaying()
    setListening(true)
    const hearing = hear(voiceLang, setDraft)
    listener.current = hearing
    hearing.text
      .then((text) => {
        // Hands-free: a completed utterance is sent as-is.
        if (text) {
          setDraft('')
          void send(text)
        }
      })
      .catch(() => undefined)
      .finally(() => {
        setListening(false)
        listener.current = null
      })
  }

  const noteCount = useChat((s) =>
    (s.conversations[`${project ?? ''}/${dashboardId ?? 'overview'}`] ?? []).reduce(
      (n, t) => n + t.blocks.filter((b) => b.kind === 'step' && b.step.name === 'save_note' && b.step.finishedAt).length,
      0,
    ),
  )
  useEffect(() => {
    if (!project) return
    currentApi()
      .knowledge()
      .then(setKnowledge)
      .catch(() => setKnowledge(null))
  }, [project, noteCount])

  // The transcript is shared: load it when the dashboard changes, then poll so
  // turns (and panels) other people add show up without a reload.
  const sync = useChat((s) => s.sync)
  const reloadDashboard = useDashboard((s) => s.reloadDashboard)
  useEffect(() => {
    if (!project || !dashboardId) return
    let cancelled = false
    void sync(true).catch(() => undefined)
    const timer = window.setInterval(() => {
      if (document.hidden || useChat.getState().sending) return
      void sync()
        .then((changed) => {
          if (changed && !cancelled) void reloadDashboard()
        })
        .catch(() => undefined)
    }, POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [project, dashboardId, sync, reloadDashboard])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [turns, conversations, dashboardId])

  if (!status?.llm.enabled) {
    return (
      <section className="notice">
        <h3 className="notice__title">Ask for a chart</h3>
        <p className="notice__text">
          Connect an OpenAI-compatible model to describe charts in plain language — PromPilot finds the metric, writes the
          PromQL and adds the panel.
        </p>
        <pre className="notice__code">{`LLM_BASE_URL=http://ollama:11434/v1
LLM_MODEL=llama3.1`}</pre>
      </section>
    )
  }

  const submit = () => {
    const text = draft
    setDraft('')
    void send(text)
  }

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="chat">
      <div className="chat__list" ref={listRef}>
        {turns.length === 0 ? (
          <div className="chat__empty">
            <p className="chat__intro">
              Describe the chart you want. The assistant searches your metrics, tests the PromQL and adds the panel —
              every step is shown below as it happens.
            </p>
            <ul className="chat__suggestions">
              {SUGGESTIONS.map((s) => (
                <li key={s}>
                  <button className="suggestion" onClick={() => void send(s)}>
                    {s}
                  </button>
                </li>
              ))}
            </ul>
            {knowledge && (
              <p className="chat__knowledge hint" title={knowledge.directory}>
                {knowledge.documents.length > 0 || knowledge.promptLoaded ? (
                  <>
                    Knows your system from{' '}
                    {knowledge.documents.map((d) => (
                      <code key={d.name}>{d.name}.md</code>
                    ))}
                    {knowledge.promptLoaded && <code>prompt.md</code>}
                  </>
                ) : (
                  <>
                    No notes about your system yet — add Markdown files to <code>knowledge/</code>.
                  </>
                )}
              </p>
            )}
          </div>
        ) : (
          turns.map((t) => <Turn key={t.id} turn={t} />)
        )}
      </div>

      {knowledge && knowledge.playbooks.length > 0 && (
        <div className="playbooks" aria-label="Playbooks">
          {knowledge.playbooks.map((pb) => (
            <button
              key={pb.name}
              className="playbook"
              title={pb.description}
              disabled={sending}
              onClick={() => void send(draft, { name: pb.name, title: pb.title })}
            >
              <Play size={11} /> {pb.title}
            </button>
          ))}
        </div>
      )}

      <form
        className="chat__composer"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          rows={2}
          placeholder={listening ? 'Listening…' : 'e.g. disk I/O per device, last 6 hours'}
          aria-label="Message"
          disabled={sending}
        />
        <div className="chat__actions">
          <span className="hint">{listening ? 'Listening… speak, then pause to send' : 'Enter to send · Shift+Enter for a new line'}</span>
          {canHear() && (
            <select
              className="chat__lang"
              value={voiceLang}
              onChange={(e) => setVoiceLang(e.target.value)}
              aria-label="Spoken language"
              title="Language you speak to the microphone"
            >
              {VOICE_LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
          )}
          {canSpeak() && (
            <button
              type="button"
              className={`btn btn--icon btn--ghost btn--sm ${voiceReplies ? 'is-on' : ''}`}
              onClick={() => {
                if (voiceReplies) stopSaying()
                setVoiceReplies(!voiceReplies)
              }}
              aria-pressed={voiceReplies}
              aria-label={voiceReplies ? 'Stop reading answers aloud' : 'Read answers aloud'}
              title={voiceReplies ? 'Voice replies on' : 'Read answers aloud'}
            >
              {voiceReplies ? <Volume2 size={15} /> : <VolumeX size={15} />}
            </button>
          )}
          {canHear() && (
            <button
              type="button"
              className={`btn btn--icon btn--ghost btn--sm ${listening ? 'is-live' : ''}`}
              onClick={toggleListening}
              disabled={sending}
              aria-pressed={listening}
              aria-label={listening ? 'Stop listening' : 'Speak your request'}
              title={listening ? 'Stop listening' : 'Speak your request'}
            >
              {listening ? <MicOff size={15} /> : <Mic size={15} />}
            </button>
          )}
          {turns.length > 0 && (
            <button type="button" className="btn btn--icon btn--ghost btn--sm" onClick={clear} disabled={sending} aria-label="Clear conversation" title="Clear conversation">
              <Eraser size={15} />
            </button>
          )}
          {sending ? (
            <button type="button" className="btn btn--icon btn--sm" onClick={stop} aria-label="Stop" title="Stop">
              <Square size={13} />
            </button>
          ) : (
            <button type="submit" className="btn btn--icon btn--primary btn--sm" disabled={!draft.trim()} aria-label="Send" title="Send">
              <ArrowUp size={16} />
            </button>
          )}
        </div>
      </form>
    </div>
  )
}

function Turn({ turn }: { turn: ChatTurn }) {
  if (turn.role === 'user') {
    return (
      <div className="msg msg--user">
        <span className="msg__prompt mono" aria-hidden="true">
          ›
        </span>
        <span>{turn.content}</span>
      </div>
    )
  }
  // Group consecutive steps into one list so they read as a single procedure.
  const groups: (Block[] | Block)[] = []
  for (const block of turn.blocks) {
    const last = groups[groups.length - 1]
    if (block.kind === 'step' && Array.isArray(last)) last.push(block)
    else groups.push(block.kind === 'step' ? [block] : block)
  }
  const lastBlock = turn.blocks[turn.blocks.length - 1]
  const waitingOnModel =
    turn.pending && (!lastBlock || (lastBlock.kind === 'step' && lastBlock.step.finishedAt !== undefined))

  return (
    <div className="msg msg--assistant">
      {turn.reasoning && <Reasoning text={turn.reasoning} />}
      {groups.map((g, i) =>
        Array.isArray(g) ? (
          <ol className="steps" key={i}>
            {g.map((b) => b.kind === 'step' && <Step key={b.step.id} step={b.step} />)}
          </ol>
        ) : (
          <Fragment key={i}>{g.kind === 'text' && g.text.trim() ? <Markdown text={g.text} /> : null}</Fragment>
        ),
      )}
      {waitingOnModel && (
        <p className="msg__thinking">
          <span className="pulse" /> Thinking…
        </p>
      )}
      {turn.error && <p className="msg__error">{turn.error}</p>}
    </div>
  )
}

/** Seconds since `since`, ticking once a second while `active`. */
function useElapsed(since: number, active: boolean): number {
  const [now, setNow] = useState(since)
  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [active])
  return Math.max(0, (now - since) / 1000)
}

function Step({ step }: { step: ToolStep }) {
  const [open, setOpen] = useState(false)
  const running = !step.finishedAt
  const icon = running ? <span className="pulse" /> : step.ok ? <Check size={13} /> : <AlertTriangle size={12} />
  const elapsed = useElapsed(step.startedAt, running)
  return (
    <li className={`step ${running ? 'step--running' : step.ok ? 'step--ok' : 'step--warn'}`}>
      <button className="step__row" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="step__icon">{icon}</span>
        <span className="step__label">{describeStep(step)}</span>
        <span className="step__meta mono">{step.summary || (running ? `${elapsed.toFixed(0)}s` : '')}</span>
        <span className="step__time mono">{running ? '' : `${elapsed < 1 ? '<1' : elapsed.toFixed(0)}s`}</span>
      </button>
      {open && (
        <pre className="step__detail">
          {JSON.stringify({ arguments: step.arguments, result: step.result }, null, 2)}
        </pre>
      )}
    </li>
  )
}

function Reasoning({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="reasoning">
      <button className="link" onClick={() => setOpen((o) => !o)}>
        {open ? 'Hide' : 'Show'} model reasoning
      </button>
      {open && <pre className="step__detail">{text}</pre>}
    </div>
  )
}
