import type { DataFrame, PanelSpec, Unit } from '../api/types'
import { formatDateTime, formatTime, formatValue } from '../format/units'
import type { ChartOption } from './useECharts'

export interface TimeseriesOptions {
  draw: 'line' | 'bars' | 'points'
  stack: boolean
  fill: number
  lineWidth: number
  legend: 'bottom' | 'right' | 'hidden'
  min: number | null
  max: number | null
}

export const SERIES_COLORS = [
  '#F0883E', // ember
  '#58A6FF', // sky
  '#3FB950', // green
  '#D2A8FF', // lilac
  '#F778BA', // pink
  '#79C0FF', // ice
  '#E3B341', // gold
  '#56D4DD', // teal
  '#FF7B72', // coral
  '#A5D6FF', // pale blue
]

export const CHART_TEXT = '#8A94A8'
export const CHART_LINE = '#232C3D'

export function readOptions(spec: PanelSpec): TimeseriesOptions {
  const o = spec.options as Partial<TimeseriesOptions>
  return {
    draw: o.draw ?? 'line',
    stack: o.stack ?? false,
    fill: o.fill ?? 0,
    lineWidth: o.lineWidth ?? 1,
    legend: o.legend ?? 'bottom',
    min: o.min ?? null,
    max: o.max ?? null,
  }
}

interface Series {
  name: string
  points: [number, number | null][]
}

/** Flatten frames into named series of [time, value] points. Non-numeric fields are ignored. */
export function seriesFromFrames(frames: DataFrame[]): Series[] {
  const out: Series[] = []
  for (const frame of frames) {
    const time = frame.fields.find((f) => f.type === 'time')
    if (!time) continue
    const numeric = frame.fields.filter((f) => f.type === 'number')
    for (const field of numeric) {
      const name = frames.length > 1 && numeric.length === 1 && field.name === 'value' ? frame.refId : field.name
      out.push({
        name,
        points: time.values.map((t, i) => [t as number, field.values[i] as number | null]),
      })
    }
  }
  return out
}

export function buildTimeseriesOption(
  spec: PanelSpec,
  frames: DataFrame[],
  timeRange: { from: number; to: number } | null,
): ChartOption {
  const opts = readOptions(spec)
  const unit: Unit = spec.unit
  const series = seriesFromFrames(frames)
  const span = timeRange ? timeRange.to - timeRange.from : 3_600_000

  const type = opts.draw === 'bars' ? 'bar' : opts.draw === 'points' ? 'scatter' : 'line'
  const showLegend = opts.legend !== 'hidden' && series.length > 0
  const legendRight = opts.legend === 'right'

  return {
    animation: false,
    color: SERIES_COLORS,
    grid: {
      left: 8,
      right: legendRight && showLegend ? 160 : 12,
      top: 12,
      bottom: showLegend && !legendRight ? 34 : 8,
      containLabel: true,
    },
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: '#121721',
      borderColor: CHART_LINE,
      textStyle: { color: '#E6EAF2', fontSize: 12, fontFamily: 'var(--font-mono)' },
      axisPointer: { type: 'line', lineStyle: { color: '#3A4559' } },
      order: 'valueDesc',
      formatter: (params: unknown) => {
        const rows = (Array.isArray(params) ? params : [params]) as {
          seriesName: string
          value: [number, number | null]
          color: string
        }[]
        if (rows.length === 0) return ''
        const head = formatDateTime(rows[0].value[0])
        const lines = rows
          .filter((r) => r.value[1] !== null && r.value[1] !== undefined)
          .map(
            (r) =>
              `<div style="display:flex;gap:10px;justify-content:space-between"><span><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${r.color};margin-right:6px"></span>${escapeHtml(r.seriesName)}</span><b>${formatValue(r.value[1], unit)}</b></div>`,
          )
        return `<div style="color:${CHART_TEXT};margin-bottom:4px">${head}</div>${lines.join('')}`
      },
    },
    legend: {
      show: showLegend,
      type: 'scroll',
      orient: legendRight ? 'vertical' : 'horizontal',
      right: legendRight ? 0 : undefined,
      top: legendRight ? 8 : undefined,
      bottom: legendRight ? undefined : 0,
      left: legendRight ? undefined : 8,
      icon: 'roundRect',
      itemWidth: 10,
      itemHeight: 3,
      textStyle: { color: CHART_TEXT, fontSize: 11, fontFamily: 'var(--font-mono)' },
      pageTextStyle: { color: CHART_TEXT },
      pageIconColor: CHART_TEXT,
      pageIconInactiveColor: CHART_LINE,
    },
    xAxis: {
      type: 'time',
      min: timeRange?.from,
      max: timeRange?.to,
      axisLine: { lineStyle: { color: CHART_LINE } },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: {
        color: CHART_TEXT,
        fontSize: 11,
        fontFamily: 'var(--font-mono)',
        hideOverlap: true,
        formatter: (value: number) => formatTime(value, span),
      },
    },
    yAxis: {
      type: 'value',
      min: opts.min ?? undefined,
      max: opts.max ?? undefined,
      scale: opts.min === null && opts.max === null,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: CHART_LINE, type: 'dashed' } },
      axisLabel: {
        color: CHART_TEXT,
        fontSize: 11,
        fontFamily: 'var(--font-mono)',
        formatter: (value: number) => formatValue(value, unit),
      },
    },
    series: series.map((s) => ({
      name: s.name,
      type,
      data: s.points,
      showSymbol: false,
      symbolSize: opts.draw === 'points' ? 4 : 0,
      connectNulls: false,
      stack: opts.stack ? 'total' : undefined,
      lineStyle: { width: opts.lineWidth },
      areaStyle: type === 'line' && opts.fill > 0 ? { opacity: opts.fill } : undefined,
      barMaxWidth: 24,
      emphasis: { focus: 'series' },
      large: s.points.length > 2000,
    })),
  }
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
}
