import { FileText, Lock, Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import type { KnowledgeStatus } from '../api/types'
import { currentApi, useDashboard } from '../store/dashboard'

type Selection = { kind: 'prompt' } | { kind: 'doc'; name: string } | { kind: 'new' }

/**
 * What the assistant knows about this project: standing instructions and
 * notes. Documents from files (mounted read-only) are listed but not editable;
 * documents created here or by the assistant live in the project database.
 */
export function NotesPanel() {
  const project = useDashboard((s) => s.project)
  const [status, setStatus] = useState<KnowledgeStatus | null>(null)
  const [selection, setSelection] = useState<Selection>({ kind: 'prompt' })
  const [text, setText] = useState('')
  const [title, setTitle] = useState('')
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [readOnly, setReadOnly] = useState(false)

  const refresh = useCallback(async () => {
    const s = await currentApi().knowledge()
    setStatus(s)
    return s
  }, [])

  useEffect(() => {
    if (!project) return
    let cancelled = false
    // oxlint-disable-next-line react/set-state-in-effect -- state follows the fetched project data
    void refresh()
      .then((s) => {
        if (cancelled) return
        setSelection({ kind: 'prompt' })
        setText(s.prompt ?? '')
        setDirty(false)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [project, refresh])

  async function open(sel: Selection) {
    setError(null)
    setSelection(sel)
    setDirty(false)
    setReadOnly(false)
    if (sel.kind === 'prompt') {
      setText(status?.prompt ?? '')
    } else if (sel.kind === 'new') {
      setTitle('')
      setText('')
    } else {
      try {
        const doc = await currentApi().knowledgeDoc(sel.name)
        setText(doc.body)
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          setReadOnly(true)
          setText('This document comes from a file in the knowledge directory. Edit it there.')
        } else setError(e instanceof Error ? e.message : String(e))
      }
    }
  }

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const api = currentApi()
      if (selection.kind === 'prompt') {
        setStatus(await api.putKnowledgePrompt(text))
      } else if (selection.kind === 'new') {
        const doc = await api.createKnowledgeDoc(title, text)
        await refresh()
        setSelection({ kind: 'doc', name: doc.name })
        setText(doc.body)
      } else {
        await api.putKnowledgeDoc(selection.name, text)
        await refresh()
      }
      setDirty(false)
    } catch (e) {
      setError(e instanceof ApiError ? e.details.join('\n') || e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (selection.kind !== 'doc') return
    setBusy(true)
    try {
      await currentApi().deleteKnowledgeDoc(selection.name)
      const s = await refresh()
      setSelection({ kind: 'prompt' })
      setText(s.prompt ?? '')
      setDirty(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const docs = status?.documents ?? []
  const editableDoc = selection.kind === 'doc' && !readOnly

  return (
    <div className="notes">
      <ul className="notes__list" aria-label="Knowledge">
        <li>
          <button className={`notes__item ${selection.kind === 'prompt' ? 'is-active' : ''}`} onClick={() => void open({ kind: 'prompt' })}>
            <FileText size={13} />
            <span className="notes__name">Instructions</span>
            <span className="notes__meta mono">{status?.prompt ? 'edited' : status?.promptFromFiles ? 'file' : '—'}</span>
          </button>
        </li>
        {docs.map((d) => (
          <li key={d.name}>
            <button
              className={`notes__item ${selection.kind === 'doc' && selection.name === d.name ? 'is-active' : ''}`}
              onClick={() => void open({ kind: 'doc', name: d.name })}
              title={d.source === 'file' ? 'From a file — read-only here' : d.source === 'assistant' ? 'Written by the assistant' : 'Editable'}
            >
              {d.source === 'file' ? <Lock size={13} /> : <FileText size={13} />}
              <span className="notes__name">{d.title}</span>
              <span className="notes__meta mono">{d.source === 'assistant' ? 'assistant' : `${d.chunks} §`}</span>
            </button>
          </li>
        ))}
        <li>
          <button className={`notes__item notes__item--new ${selection.kind === 'new' ? 'is-active' : ''}`} onClick={() => void open({ kind: 'new' })}>
            <Plus size={13} />
            <span className="notes__name">New document</span>
          </button>
        </li>
      </ul>

      <div className="notes__editor">
        {selection.kind === 'new' && (
          <label className="field">
            <span>Title</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Checkout service" autoFocus />
          </label>
        )}
        <p className="hint">
          {selection.kind === 'prompt'
            ? 'Standing instructions sent with every message: what the system is, SLOs, preferred breakdowns, house rules.'
            : selection.kind === 'new'
              ? 'Markdown. Headings become searchable sections; “- `metric` — meaning” bullets annotate metrics.'
              : readOnly
                ? 'Read-only.'
                : 'Markdown. Headings become searchable sections; “- `metric` — meaning” bullets annotate metrics.'}
        </p>
        {selection.kind === 'prompt' && status?.promptFromFiles && (
          <details className="notes__filepart">
            <summary>
              <Lock size={12} /> From <code>prompt.md</code> files (read-only, applied first)
            </summary>
            <pre className="notes__pre">{status.promptFromFiles}</pre>
          </details>
        )}
        <textarea
          className="notes__text mono"
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            setDirty(true)
          }}
          readOnly={readOnly}
          spellCheck={false}
          rows={14}
        />
        {error && (
          <p className="form__error" role="alert">
            {error}
          </p>
        )}
        <div className="form__actions">
          <button className="btn btn--primary btn--sm" onClick={() => void save()} disabled={busy || readOnly || (!dirty && selection.kind !== 'new') || (selection.kind === 'new' && !title.trim())}>
            {busy ? 'Saving…' : selection.kind === 'new' ? 'Create' : 'Save'}
          </button>
          {editableDoc && (
            <button className="btn btn--ghost btn--sm modal__danger" onClick={() => void remove()} disabled={busy} title="Delete this document">
              <Trash2 size={13} /> Delete
            </button>
          )}
          {status && (
            <span className="hint notes__count">
              {status.chunks} sections · {status.metricNotes} metric notes
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
