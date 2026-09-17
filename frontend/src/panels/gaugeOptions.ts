import type { PanelSpec } from '../api/types'
import { CHART_THEMES, THRESHOLD_COLORS, type Theme } from '../theme'
import type { Reduce } from './reduce'

type ThresholdColor = keyof (typeof THRESHOLD_COLORS)['light']

export interface GaugeOptions {
  min: number
  max: number
  reduce: Reduce
  decimals: number | null
  thresholds: { value: number; color: ThresholdColor }[]
  showThresholdMarkers: boolean
}

export function readGaugeOptions(spec: PanelSpec): GaugeOptions {
  const o = spec.options as Partial<GaugeOptions>
  return {
    min: o.min ?? 0,
    max: o.max ?? 1,
    reduce: o.reduce ?? 'last',
    decimals: o.decimals ?? null,
    thresholds: o.thresholds ?? [],
    showThresholdMarkers: o.showThresholdMarkers ?? true,
  }
}

/** ECharts axisLine colour stops: [fraction, colour] for each threshold band. */
export function bands(opts: GaugeOptions, theme: Theme): [number, string][] {
  const palette = THRESHOLD_COLORS[theme]
  const span = opts.max - opts.min || 1
  const sorted = [...opts.thresholds].sort((a, b) => a.value - b.value)
  if (sorted.length === 0) return [[1, CHART_THEMES[theme].line]]
  const out: [number, string][] = []
  let color: string = palette.green
  for (const t of sorted) {
    const f = Math.min(1, Math.max(0, (t.value - opts.min) / span))
    out.push([f, color])
    color = palette[t.color]
  }
  out.push([1, color])
  return out.filter(([f], i, arr) => i === 0 || f > arr[i - 1][0])
}
