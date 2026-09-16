import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { UNITS, type NewPanelSpec, type PanelSpec, type Unit } from '../api/types'

interface FormState {
  title: string
  expr: string
  legend: string
  unit: Unit
  draw: 'line' | 'bars' | 'points'
  stack: boolean
  legendPlacement: 'bottom' | 'right' | 'hidden'
}

const EMPTY: FormState = {
  title: '',
  expr: '',
  legend: '',
  unit: 'short',
  draw: 'line',
  stack: false,
  legendPlacement: 'bottom',
}

function fromSpec(spec: PanelSpec): FormState {
  const o = spec.options as Partial<{ draw: FormState['draw']; stack: boolean; legend: FormState['legendPlacement'] }>
  return {
    title: spec.title,
    expr: spec.queries[0]?.expr ?? '',
    legend: spec.queries[0]?.legend ?? '',
    unit: spec.unit,
    draw: o.draw ?? 'line',
    stack: o.stack ?? false,
    legendPlacement: o.legend ?? 'bottom',
  }
}

function toSpec(form: FormState, editing: PanelSpec | null): NewPanelSpec {
  // The form edits the first query; any further queries on the panel are kept as they are.
  const rest = editing?.queries.slice(1) ?? []
  return {
    type: editing?.type ?? 'timeseries',
    title: form.title.trim() || form.expr.trim(),
    queries: [{ refId: 'A', expr: form.expr.trim(), legend: form.legend.trim() || null, instant: false }, ...rest],
    unit: form.unit,
    options: { draw: form.draw, stack: form.stack, legend: form.legendPlacement },
  }
}

interface Props {
  editing: PanelSpec | null
  onSubmit: (spec: NewPanelSpec) => Promise<void>
  onCancel: () => void
}

/** Manual panel authoring. Stays available next to the chat as the "I know the PromQL" path.
 *  Remounted by the parent (via `key`) when the edited panel changes. */
export function PanelForm({ editing, onSubmit, onCancel }: Props) {
  const [form, setForm] = useState<FormState>(editing ? fromSpec(editing) : EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }))

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!form.expr.trim()) {
      setError('Enter a PromQL expression.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await onSubmit(toSpec(form, editing))
      if (!editing) setForm(EMPTY)
    } catch (err) {
      setError(err instanceof ApiError ? err.details.join('\n') || err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      <h3 className="form__title">{editing ? 'Edit panel' : 'Add a panel'}</h3>

      <label className="field">
        <span>PromQL</span>
        <textarea
          className="mono"
          rows={3}
          value={form.expr}
          onChange={(e) => set('expr', e.target.value)}
          placeholder='rate(node_cpu_seconds_total{mode!="idle"}[5m])'
          spellCheck={false}
          required
        />
      </label>

      <label className="field">
        <span>Title</span>
        <input value={form.title} onChange={(e) => set('title', e.target.value)} placeholder="Defaults to the query" />
      </label>

      <div className="field-row">
        <label className="field">
          <span>Legend</span>
          <input
            className="mono"
            value={form.legend}
            onChange={(e) => set('legend', e.target.value)}
            placeholder="{{instance}}"
            spellCheck={false}
          />
        </label>
        <label className="field">
          <span>Unit</span>
          <select value={form.unit} onChange={(e) => set('unit', e.target.value as Unit)}>
            {UNITS.map((u) => (
              <option key={u.value} value={u.value}>
                {u.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="field-row">
        <label className="field">
          <span>Draw</span>
          <select value={form.draw} onChange={(e) => set('draw', e.target.value as FormState['draw'])}>
            <option value="line">Lines</option>
            <option value="bars">Bars</option>
            <option value="points">Points</option>
          </select>
        </label>
        <label className="field">
          <span>Legend placement</span>
          <select
            value={form.legendPlacement}
            onChange={(e) => set('legendPlacement', e.target.value as FormState['legendPlacement'])}
          >
            <option value="bottom">Bottom</option>
            <option value="right">Right</option>
            <option value="hidden">Hidden</option>
          </select>
        </label>
      </div>

      <label className="check">
        <input type="checkbox" checked={form.stack} onChange={(e) => set('stack', e.target.checked)} />
        Stack series
      </label>

      {error && (
        <p className="form__error" role="alert">
          {error}
        </p>
      )}

      <div className="form__actions">
        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? 'Saving…' : editing ? 'Save changes' : 'Add panel'}
        </button>
        {editing && (
          <button className="btn btn--ghost" type="button" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}
