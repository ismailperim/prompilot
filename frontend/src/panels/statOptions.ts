import type { PanelSpec } from '../api/types'
import { THRESHOLD_COLORS, type Theme } from '../theme'
import type { Reduce } from './reduce'

type ThresholdColor = 'green' | 'yellow' | 'orange' | 'red' | 'blue' | 'purple'

export interface StatOptions {
  reduce: Reduce
  colorMode: 'none' | 'value' | 'background'
  graph: boolean
  decimals: number | null
  thresholds: { value: number; color: ThresholdColor }[]
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
export function thresholdColor(
  value: number | null,
  thresholds: StatOptions['thresholds'],
  theme: Theme = 'light',
): string {
  const palette = THRESHOLD_COLORS[theme]
  if (value === null) return palette.green
  let color: string = palette.green
  for (const t of [...thresholds].sort((a, b) => a.value - b.value)) {
    if (value >= t.value) color = palette[t.color]
  }
  return color
}
