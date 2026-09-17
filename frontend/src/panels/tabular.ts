import type { DataFrame } from '../api/types'

export interface Tabular {
  columns: string[]
  rows: (string | number | null)[][]
}

/**
 * Frames as a flat table for inspection and export. A wide frame (time + numeric
 * fields) becomes one row per timestamp; a table-shaped frame (label strings +
 * value) is already rows.
 */
export function frameToTabular(frame: DataFrame): Tabular {
  const time = frame.fields.find((f) => f.type === 'time')
  const strings = frame.fields.filter((f) => f.type === 'string')
  const numbers = frame.fields.filter((f) => f.type === 'number')
  const length = frame.fields[0]?.values.length ?? 0

  if (strings.length > 0) {
    const columns = [...(time ? ['time'] : []), ...strings.map((f) => f.name), ...numbers.map((f) => f.name)]
    const rows: Tabular['rows'] = []
    for (let i = 0; i < length; i++) {
      rows.push([
        ...(time ? [isoOf(time.values[i])] : []),
        ...strings.map((f) => f.values[i] ?? null),
        ...numbers.map((f) => f.values[i] ?? null),
      ])
    }
    return { columns, rows }
  }

  const columns = [...(time ? ['time'] : []), ...numbers.map((f) => f.name)]
  const rows: Tabular['rows'] = []
  for (let i = 0; i < length; i++) {
    rows.push([...(time ? [isoOf(time.values[i])] : []), ...numbers.map((f) => f.values[i] ?? null)])
  }
  return { columns, rows }
}

function isoOf(value: string | number | null): string | null {
  return typeof value === 'number' ? new Date(value).toISOString() : value
}

export function toCsv(table: Tabular): string {
  const escape = (v: string | number | null) => {
    if (v === null || v === undefined) return ''
    const s = String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return [table.columns.map(escape).join(','), ...table.rows.map((r) => r.map(escape).join(','))].join('\n')
}
