import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import type { SystemStatus } from '../api/types'
import { describeStep, useChat, type Block, type ChatTurn, type ToolStep } from './store'

const SUGGESTIONS = [
  'Show CPU usage per core as a percentage',
  'Memory available over time',
  'Network throughput per interface, received and transmitted',
  'How long do Prometheus scrapes take?',
]

export function ChatPanel({ status }: { status: SystemStatus | null }) {
  const turns = useChat((s) => s.turns)
  const sending = useChat((s) => s.sending)
  const send = useChat((s) => s.send)
  const stop = useChat((s) => s.stop)
  const clear = useChat((s) => s.clear)
  const [draft, setDraft] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [turns])

  if (!status?.llm.enabled) {
    return (
      <section className="card card--chat">
        <h3 className="card__title">Ask for a chart</h3>
        <p className="card__text">
          Connect an OpenAI-compatible model to describe charts in plain language — PromPilot finds the metric, writes the
          PromQL and adds the panel.
        </p>
        <pre className="card__code">{`LLM_BASE_URL=http://ollama:11434/v1
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
            <p className="card__text">
              Describe the chart you want. The assistant searches your metrics, tests the PromQL and adds the panel.
            </p>
            <div className="chat__suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chip chip--suggestion" onClick={() => void send(s)}>
                  {s}
                </button>
              ))}
            </div>
            <p className="hint">
              Model: <code>{status.llm.model}</code>
            </p>
          </div>
        ) : (
          turns.map((t) => <Turn key={t.id} turn={t} />)
        )}
      </div>

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
          placeholder="e.g. disk I/O per device, last 6 hours"
          aria-label="Message"
          disabled={sending}
        />
        <div className="chat__actions">
          {turns.length > 0 && (
            <button type="button" className="btn btn--ghost btn--sm" onClick={clear} disabled={sending}>
              Clear
            </button>
          )}
          {sending ? (
            <button type="button" className="btn btn--sm" onClick={stop}>
              Stop
            </button>
          ) : (
            <button type="submit" className="btn btn--primary btn--sm" disabled={!draft.trim()}>
              Send
            </button>
          )}
        </div>
      </form>
    </div>
  )
}

function Turn({ turn }: { turn: ChatTurn }) {
  if (turn.role === 'user') {
    return <div className="msg msg--user">{turn.content}</div>
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
          <p className="msg__text" key={i}>
            {g.kind === 'text' ? g.text.trim() : null}
          </p>
        ),
      )}
      {waitingOnModel && (
        <p className="msg__thinking">
          <span className="panel__pulse" /> Thinking…
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
  const icon = running ? <span className="panel__pulse" /> : step.ok ? '✓' : '!'
  const elapsed = useElapsed(step.startedAt, running)
  return (
    <li className={`step ${running ? 'step--running' : step.ok ? 'step--ok' : 'step--warn'}`}>
      <button className="step__row" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="step__icon">{icon}</span>
        <span className="step__label">{describeStep(step)}</span>
        <span className="step__meta">{step.summary || (running ? `${elapsed.toFixed(0)}s` : '')}</span>
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
