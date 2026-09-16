import type { Unit } from '../api/types'

const SI = ['', 'k', 'M', 'G', 'T', 'P']
const IEC = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']
const DEC = ['B', 'kB', 'MB', 'GB', 'TB', 'PB']

function trim(n: number, digits: number): string {
  const s = n.toFixed(digits)
  return s.includes('.') ? s.replace(/\.?0+$/, '') : s
}

function scaled(value: number, base: number, suffixes: string[], digits = 2): string {
  const abs = Math.abs(value)
  if (abs === 0) return `0 ${suffixes[0]}`.trim()
  let i = 0
  let v = abs
  while (v >= base && i < suffixes.length - 1) {
    v /= base
    i++
  }
  const sign = value < 0 ? '-' : ''
  return `${sign}${trim(v, digits)}${suffixes[i] ? ` ${suffixes[i]}` : ''}`.trim()
}

/** Compact number: 1234 → "1.23k". No unit suffix. */
export function formatShort(value: number, digits = 2): string {
  const abs = Math.abs(value)
  if (abs < 1000) return trim(value, abs < 1 ? 3 : digits)
  return scaled(value, 1000, SI, digits).replace(' ', '')
}

export function formatSeconds(value: number): string {
  if (value === 0) return '0 s'
  const abs = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (abs < 0.001) return `${sign}${trim(abs * 1e6, 1)} µs`
  if (abs < 1) return `${sign}${trim(abs * 1e3, 1)} ms`
  if (abs < 60) return `${sign}${trim(abs, 2)} s`
  if (abs < 3600) return `${sign}${trim(abs / 60, 1)} min`
  if (abs < 86400) return `${sign}${trim(abs / 3600, 1)} h`
  return `${sign}${trim(abs / 86400, 1)} d`
}

/** Human-readable value for a Grafana unit ID. Mirrors Grafana's defaults closely enough for axes and tooltips. */
export function formatValue(value: number | null | undefined, unit: Unit): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'
  switch (unit) {
    case 'none':
      return trim(value, 3)
    case 'short':
      return formatShort(value)
    case 'percent':
      return `${trim(value, 1)}%`
    case 'percentunit':
      return `${trim(value * 100, 1)}%`
    case 'bytes':
      return scaled(value, 1024, IEC)
    case 'decbytes':
      return scaled(value, 1000, DEC)
    case 'Bps':
      return `${scaled(value, 1000, DEC)}/s`
    case 'bps':
      return `${scaled(value, 1000, SI.map((s) => `${s}b`))}/s`
    case 's':
      return formatSeconds(value)
    case 'ms':
      return formatSeconds(value / 1000)
    case 'ops':
      return `${formatShort(value)} ops/s`
    case 'reqps':
      return `${formatShort(value)} req/s`
    case 'rps':
      return `${formatShort(value)} rd/s`
    case 'wps':
      return `${formatShort(value)} wr/s`
  }
}

const pad = (n: number) => String(n).padStart(2, '0')

/** Axis label for a timestamp; shows the date once the range spans more than a day. */
export function formatTime(ms: number, spanMs: number): string {
  const d = new Date(ms)
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  if (spanMs > 7 * 86_400_000) return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  if (spanMs > 86_400_000) return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`
  if (spanMs <= 5 * 60_000) return `${hm}:${pad(d.getSeconds())}`
  return hm
}

export function formatDateTime(ms: number): string {
  const d = new Date(ms)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
