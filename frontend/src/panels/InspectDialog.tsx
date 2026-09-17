import { Check, Copy, Download } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import type { DataFrame, PanelSpec } from '../api/types'
import { formatValue } from '../format/units'
import { frameToTabular, toCsv } from './tabular'

interface Props {
  spec: PanelSpec
  frames: DataFrame[]
  onClose: () => void
}

const MAX_ROWS = 500

/** The numbers behind a panel: one table per query, with CSV export and the PromQL to copy. */
export function InspectDialog({ spec, frames, onClose }: Props) {
  const [refId, setRefId] = useState(frames[0]?.refId ?? spec.queries[0]?.refId ?? 'A')
  const [copied, setCopied] = useState<string | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const frame = frames.find((f) => f.refId === refId) ?? frames[0]
  const query = spec.queries.find((q) => q.refId === refId) ?? spec.queries[0]
  const table = useMemo(() => (frame ? frameToTabular(frame) : { columns: [], rows: [] }), [frame])
  const shown = table.rows.slice(0, MAX_ROWS)

  const copy = async (what: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(what)
      window.setTimeout(() => setCopied(null), 1500)
    } catch {
      /* clipboard unavailable (e.g. http on a remote host) */
    }
  }

  const download = () => {
    const blob = new Blob([toCsv(table)], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${spec.title.replace(/[^\w-]+/g, '_')}_${refId}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Grid items are transformed, which would trap a fixed-position dialog inside the panel.
  return createPortal(
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="inspect-title" onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal__panel modal__panel--wide">
        <div className="inspect__head">
          <h2 className="modal__title" id="inspect-title">
            {spec.title}
          </h2>
          {spec.queries.length > 1 && (
            <div className="type-picker inspect__queries" role="tablist" aria-label="Query">
              {spec.queries.map((q) => (
                <button key={q.refId} role="tab" aria-selected={q.refId === refId} className={`type-picker__item ${q.refId === refId ? 'is-active' : ''}`} onClick={() => setRefId(q.refId)}>
                  {q.refId}
                </button>
              ))}
            </div>
          )}
        </div>

        {query && (
          <div className="inspect__query">
            <code className="inspect__expr">{query.expr}</code>
            <button className="btn btn--icon btn--ghost btn--sm" onClick={() => void copy('promql', query.expr)} aria-label="Copy PromQL" title="Copy PromQL">
              {copied === 'promql' ? <Check size={14} /> : <Copy size={14} />}
            </button>
          </div>
        )}

        <p className="hint">
          {table.rows.length} {table.rows.length === 1 ? 'row' : 'rows'} · {Math.max(table.columns.length - 1, 0)}{' '}
          {table.columns.length - 1 === 1 ? 'series' : 'series'}
          {table.rows.length > MAX_ROWS ? ` · showing the first ${MAX_ROWS}` : ''}
        </p>

        <div className="inspect__table">
          <table className="table">
            <thead>
              <tr>
                {table.columns.map((c) => (
                  <th key={c} className={c === 'time' ? '' : 'table__num'}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j} className={`mono ${typeof cell === 'number' ? 'table__num' : ''}`}>
                      {typeof cell === 'number' ? formatValue(cell, spec.unit) : (cell ?? '')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="modal__actions">
          <button className="btn btn--sm" onClick={download}>
            <Download size={14} /> Download CSV
          </button>
          <button className="btn btn--sm" onClick={() => void copy('csv', toCsv(table))}>
            {copied === 'csv' ? <Check size={14} /> : <Copy size={14} />} Copy CSV
          </button>
          <span className="modal__spacer" />
          <button className="btn btn--ghost" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
