import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { UNITS, type NewPanelSpec, type PanelSpec, type Unit } from '../api/types'

export type PanelType = 'timeseries' | 'stat' | 'table' | 'gauge'

export interface FormState {
  type: PanelType
  title: string
  expr: string
  legend: string
  unit: Unit
  // timeseries
  draw: 'line' | 'bars' | 'points'
  stack: boolean
  legendPlacement: 'bottom' | 'right' | 'hidden'
  // stat
  reduce: 'last' | 'mean' | 'max' | 'min' | 'sum'
  colorMode: 'none' | 'value' | 'background'
  // table
  sortBy: string
  limit: number
  // gauge
  min: number
  max: number
}

const EMPTY: FormState = {
  type: 'timeseries',
  title: '',
  expr: '',
  legend: '',
  unit: 'short',
  draw: 'line',
  stack: false,
  legendPlacement: 'bottom',
  reduce: 'last',
  colorMode: 'value',
  sortBy: 'value',
  limit: 100,
  min: 0,
  max: 1,
}

const TYPES: { value: PanelType; label: string; hint: string }[] = [
  { value: 'timeseries', label: 'Time series', hint: 'Values over time' },
  { value: 'stat', label: 'Stat', hint: 'One big number per series' },
  { value: 'table', label: 'Table', hint: 'Rows per series, instant query' },
  { value: 'gauge', label: 'Gauge', hint: 'Current value on a dial' },
]

function fromSpec(spec: PanelSpec): FormState {
  const o = spec.options as Record<string, unknown>
  const type = (['timeseries', 'stat', 'table', 'gauge'] as const).includes(spec.type as PanelType) ? (spec.type as PanelType) : 'timeseries'
  return {
    ...EMPTY,
    type,
    title: spec.title,
    expr: spec.queries[0]?.expr ?? '',
    legend: spec.queries[0]?.legend ?? '',
    unit: spec.unit,
    draw: (o.draw as FormState['draw']) ?? 'line',
    stack: (o.stack as boolean) ?? false,
    legendPlacement: (o.legend as FormState['legendPlacement']) ?? 'bottom',
    reduce: (o.reduce as FormState['reduce']) ?? 'last',
    colorMode: (o.colorMode as FormState['colorMode']) ?? 'value',
    sortBy: (o.sortBy as string) ?? 'value',
    limit: (o.limit as number) ?? 100,
    min: (o.min as number) ?? 0,
    max: (o.max as number) ?? 1,
  }
}

function optionsFor(form: FormState): Record<string, unknown> {
  switch (form.type) {
    case 'timeseries':
      return { draw: form.draw, stack: form.stack, legend: form.legendPlacement }
    case 'stat':
      return { reduce: form.reduce, colorMode: form.colorMode }
    case 'table':
      return { sortBy: form.sortBy.trim() || null, limit: form.limit }
    case 'gauge':
      return { min: form.min, max: form.max, reduce: form.reduce }
  }
}

function toSpec(form: FormState, editing: PanelSpec | null): NewPanelSpec {
  // The form edits the first query; any further queries on the panel are kept as they are.
  const rest = editing?.type === form.type ? (editing?.queries.slice(1) ?? []) : []
  return {
    type: form.type,
    title: form.title.trim() || form.expr.trim(),
    queries: [
      { refId: 'A', expr: form.expr.trim(), legend: form.legend.trim() || null, instant: form.type === 'table' },
      ...rest,
    ],
    unit: form.unit,
    options: optionsFor(form),
  }
}

interface Props {
  editing: PanelSpec | null
  /** Pre-filled values for a new panel (e.g. picked from the metric browser). */
  initial?: Partial<FormState>
  onSubmit: (spec: NewPanelSpec) => Promise<void>
  onCancel: () => void
}

/** Manual panel authoring. Stays available next to the chat as the "I know the PromQL" path.
 *  Remounted by the parent (via `key`) when the edited panel changes. */
export function PanelForm({ editing, initial, onSubmit, onCancel }: Props) {
  const [form, setForm] = useState<FormState>(editing ? fromSpec(editing) : { ...EMPTY, ...initial })
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
      <div className="form__head">
        <h3 className="form__title">{editing ? 'Edit panel' : 'Add a panel'}</h3>
        {editing && <code className="form__id">{editing.id.slice(0, 8)}</code>}
      </div>

      <div className="type-picker" role="radiogroup" aria-label="Panel type">
        {TYPES.map((t) => (
          <button
            key={t.value}
            type="button"
            role="radio"
            aria-checked={form.type === t.value}
            className={`type-picker__item ${form.type === t.value ? 'is-active' : ''}`}
            onClick={() => set('type', t.value)}
            disabled={editing !== null && editing.type !== t.value}
            title={t.hint}
          >
            {t.label}
          </button>
        ))}
      </div>

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

      {form.type === 'timeseries' && (
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

      )}

      {form.type === 'timeseries' && (
        <label className="check">
          <input type="checkbox" checked={form.stack} onChange={(e) => set('stack', e.target.checked)} />
          Stack series
        </label>
      )}

      {form.type === 'stat' && (
        <div className="field-row">
          <label className="field">
            <span>Reduce</span>
            <select value={form.reduce} onChange={(e) => set('reduce', e.target.value as FormState['reduce'])}>
              <option value="last">Last value</option>
              <option value="mean">Mean</option>
              <option value="max">Max</option>
              <option value="min">Min</option>
              <option value="sum">Sum</option>
            </select>
          </label>
          <label className="field">
            <span>Color</span>
            <select value={form.colorMode} onChange={(e) => set('colorMode', e.target.value as FormState['colorMode'])}>
              <option value="value">Value</option>
              <option value="background">Background</option>
              <option value="none">None</option>
            </select>
          </label>
        </div>
      )}

      {form.type === 'gauge' && (
        <div className="field-row">
          <label className="field">
            <span>Min</span>
            <input type="number" step="any" value={form.min} onChange={(e) => set('min', Number(e.target.value))} />
          </label>
          <label className="field">
            <span>Max</span>
            <input type="number" step="any" value={form.max} onChange={(e) => set('max', Number(e.target.value))} />
          </label>
        </div>
      )}

      {form.type === 'table' && (
        <div className="field-row">
          <label className="field">
            <span>Sort by</span>
            <input className="mono" value={form.sortBy} onChange={(e) => set('sortBy', e.target.value)} placeholder="value or a label" />
          </label>
          <label className="field">
            <span>Row limit</span>
            <input type="number" min={1} max={1000} value={form.limit} onChange={(e) => set('limit', Number(e.target.value) || 100)} />
          </label>
        </div>
      )}

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
