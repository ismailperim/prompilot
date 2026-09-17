import { Clock } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { TimeRange } from '../api/types'
import { formatDateTime } from '../format/units'
import { QUICK_RANGES } from './timeRanges'

interface Props {
  value: TimeRange
  resolved: { from: number; to: number } | null
  onChange: (range: TimeRange) => void
}

export function TimeRangePicker({ value, resolved, onChange }: Props) {
  const [custom, setCustom] = useState(false)
  const [draft, setDraft] = useState(value)
  const root = useRef<HTMLDivElement>(null)
  const isQuick = value.to === 'now' && QUICK_RANGES.some((q) => q.from === value.from)

  // Close the custom-range popover on outside click or Escape.
  useEffect(() => {
    if (!custom) return
    const onPointerDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setCustom(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setCustom(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [custom])

  return (
    <div className="timepicker" ref={root}>
      <div className="segmented" role="group" aria-label="Time range">
        <span className="segmented__icon" aria-hidden="true">
          <Clock size={14} />
        </span>
        {QUICK_RANGES.map((q) => (
          <button
            key={q.from}
            className={`segmented__item ${value.from === q.from && value.to === 'now' ? 'is-active' : ''}`}
            onClick={() => onChange({ from: q.from, to: 'now' })}
          >
            {q.label}
          </button>
        ))}
        <button
          className={`segmented__item ${!isQuick || custom ? 'is-active' : ''}`}
          onClick={() => {
            setDraft(value)
            setCustom((c) => !c)
          }}
          aria-expanded={custom}
        >
          Custom
        </button>
      </div>

      {resolved && (
        <span className="timepicker__resolved mono" title="Resolved absolute range">
          {formatDateTime(resolved.from)} <span className="timepicker__arrow">→</span> {formatDateTime(resolved.to)}
        </span>
      )}

      {custom && (
        <form
          className="popover timepicker__custom"
          onSubmit={(e) => {
            e.preventDefault()
            onChange(draft)
            setCustom(false)
          }}
        >
          <label className="field">
            <span>From</span>
            <input className="mono" value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} spellCheck={false} autoFocus />
          </label>
          <label className="field">
            <span>To</span>
            <input className="mono" value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} spellCheck={false} />
          </label>
          <p className="hint">
            Grafana syntax: <code>now-1h</code>, <code>now/d</code>, <code>now-1d/d</code>, ISO dates or epoch ms.
          </p>
          <button className="btn btn--primary btn--sm" type="submit">
            Apply range
          </button>
        </form>
      )}
    </div>
  )
}
