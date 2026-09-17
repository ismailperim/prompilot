import type { DataFrame } from '../api/types'

export type Reduce = 'last' | 'mean' | 'max' | 'min' | 'sum'

export interface SeriesValue {
  name: string
  labels: Record<string, string>
  value: number | null
  points: [number, number | null][]
}

const numbers = (values: (number | string | null)[]): number[] =>
  values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v))

export function reduceValues(values: (number | string | null)[], how: Reduce): number | null {
  const nums = numbers(values)
  if (nums.length === 0) return null
  switch (how) {
    case 'last':
      return nums[nums.length - 1]
    case 'mean':
      return nums.reduce((a, b) => a + b, 0) / nums.length
    case 'max':
      return Math.max(...nums)
    case 'min':
      return Math.min(...nums)
    case 'sum':
      return nums.reduce((a, b) => a + b, 0)
  }
}

/**
 * One value per series from any frame shape: wide (time + number fields, from range
 * queries) or table-shaped (label string fields + a `value` field, from instant queries).
 */
export function seriesValues(frames: DataFrame[], how: Reduce): SeriesValue[] {
  const out: SeriesValue[] = []
  for (const frame of frames) {
    const time = frame.fields.find((f) => f.type === 'time')
    const numeric = frame.fields.filter((f) => f.type === 'number')
    const strings = frame.fields.filter((f) => f.type === 'string')

    if (strings.length > 0 && numeric.length === 1 && numeric[0].name === 'value') {
      // table-shaped: each row is a series
      const value = numeric[0]
      for (let row = 0; row < value.values.length; row++) {
        const labels: Record<string, string> = {}
        for (const s of strings) labels[s.name] = String(s.values[row] ?? '')
        const v = value.values[row]
        out.push({
          name: labelsToName(labels),
          labels,
          value: typeof v === 'number' ? v : null,
          points: time ? [[time.values[row] as number, typeof v === 'number' ? v : null]] : [],
        })
      }
      continue
    }

    for (const field of numeric) {
      out.push({
        name: field.name,
        labels: field.labels ?? {},
        value: reduceValues(field.values, how),
        points: time ? time.values.map((t, i) => [t as number, field.values[i] as number | null]) : [],
      })
    }
  }
  return out
}

function labelsToName(labels: Record<string, string>): string {
  const pairs = Object.entries(labels).filter(([k]) => k !== '__name__')
  if (pairs.length === 0) return labels.__name__ ?? 'value'
  return pairs.map(([k, v]) => `${k}=${v}`).join(', ')
}
