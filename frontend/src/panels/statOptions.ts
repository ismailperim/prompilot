import type { PanelSpec } from '../api/types'
import type { Reduce } from './reduce'

type ThresholdColor = 'green' | 'yellow' | 'orange' | 'red' | 'blue' | 'purple'

export interface StatOptions {
  reduce: Reduce
  colorMode: 'none' | 'value' | 'background'
  graph: boolean
  decimals: number | null
  thresholds: { value: number; color: ThresholdColor }[]
}

const COLORS: Record<ThresholdColor, string> = {
  green: '#3fb950',
  yellow: '#d29922',
  orange: '#f0883e',
  red: '#f47067',
  blue: '#58a6ff',
  purple: '#d2a8ff',
}

export function readStatOptions(spec: PanelSpec): StatOptions {
  const o = spec.options as Partial<StatOptions>
  return {
    reduce: o.reduce ?? 'last',
    colorMode: o.colorMode ?? 'value',
    graph: o.graph ?? true,
    decimals: o.decimals ?? null,
    thresholds: o.thresholds ?? [],
  }
}

/** Grafana semantics: base colour green, each threshold applies from its value upwards. */
export function thresholdColor(value: number | null, thresholds: StatOptions['thresholds']): string {
  if (value === null) return COLORS.green
  let color: string = COLORS.green
  for (const t of [...thresholds].sort((a, b) => a.value - b.value)) {
    if (value >= t.value) color = COLORS[t.color]
  }
  return color
}
