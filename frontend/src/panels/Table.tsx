import { ArrowDown, ArrowUp } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { PanelSpec } from '../api/types'
import { formatValue } from '../format/units'
import { seriesValues } from './reduce'
import type { PanelRendererProps } from './types'

interface TableOptions {
  sortBy: string | null
  sortDesc: boolean
  limit: number
  hideColumns: string[]
  valueColumn: string
}

function readTableOptions(spec: PanelSpec): TableOptions {
  const o = spec.options as Partial<TableOptions>
  return {
    sortBy: o.sortBy ?? null,
    sortDesc: o.sortDesc ?? true,
    limit: o.limit ?? 100,
    hideColumns: o.hideColumns ?? [],
    valueColumn: o.valueColumn ?? 'Value',
  }
}

/** Sort key for the value column; label names can't contain '$', so it never collides. */
const VALUE_KEY = '$value'

export function Table({ spec, frames }: PanelRendererProps) {
  const opts = readTableOptions(spec)
  const [sort, setSort] = useState<{ key: string; desc: boolean }>({
    key: opts.sortBy && opts.sortBy.toLowerCase() !== 'value' ? opts.sortBy : VALUE_KEY,
    desc: opts.sortDesc,
  })

  const rows = useMemo(() => seriesValues(frames, 'last'), [frames])
  const columns = useMemo(() => {
    const hidden = new Set(['__name__', ...opts.hideColumns])
    const keys = new Set<string>()
    for (const r of rows) for (const k of Object.keys(r.labels)) if (!hidden.has(k)) keys.add(k)
    return [...keys].sort()
  }, [rows, opts.hideColumns])

  const sorted = useMemo(() => {
    const dir = sort.desc ? -1 : 1
    const copy = [...rows]
    copy.sort((a, b) => {
      if (sort.key === VALUE_KEY) {
        return ((a.value ?? -Infinity) - (b.value ?? -Infinity)) * dir
      }
      return (a.labels[sort.key] ?? '').localeCompare(b.labels[sort.key] ?? '') * dir
    })
    return copy.slice(0, opts.limit)
  }, [rows, sort, opts.limit])

  if (rows.length === 0) {
    return (
      <div className="panel-message">
        <strong>No data</strong>
        <span>The query returned no series.</span>
      </div>
    )
  }

  const toggle = (key: string) =>
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: key === VALUE_KEY }))
  const indicator = (key: string) =>
    sort.key === key ? sort.desc ? <ArrowDown size={12} /> : <ArrowUp size={12} /> : null

  return (
    <div className="table-host">
      <table className="table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>
                <button className="table__sort" onClick={() => toggle(c)}>
                  {c} {indicator(c)}
                </button>
              </th>
            ))}
            <th className="table__num">
              <button className="table__sort" onClick={() => toggle(VALUE_KEY)}>
                {opts.valueColumn} {indicator(VALUE_KEY)}
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c} className="mono" title={r.labels[c]}>
                  {r.labels[c] ?? ''}
                </td>
              ))}
              <td className="table__num mono">{formatValue(r.value, spec.unit)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > sorted.length && (
        <p className="table__more">
          {sorted.length} of {rows.length} rows
        </p>
      )}
    </div>
  )
}
