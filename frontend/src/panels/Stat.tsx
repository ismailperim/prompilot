import { useMemo } from 'react'
import type { PanelSpec } from '../api/types'
import { formatValue } from '../format/units'
import { seriesValues, type SeriesValue } from './reduce'
import { readStatOptions, thresholdColor, type StatOptions } from './statOptions'
import { CHART_THEMES, useTheme, type Theme } from '../theme'
import type { PanelRendererProps } from './types'
import { useECharts, type ChartOption } from './useECharts'

export function Stat({ spec, frames, timeRange }: PanelRendererProps) {
  const theme = useTheme((s) => s.theme)
  const opts = readStatOptions(spec)
  const series = useMemo(() => seriesValues(frames, opts.reduce), [frames, opts.reduce])
  const shown = series.slice(0, 12)

  if (shown.length === 0) {
    return (
      <div className="panel-message">
        <strong>No data</strong>
        <span>The query returned no series for this time range.</span>
      </div>
    )
  }

  return (
    <div className={`stat stat--${shown.length > 1 ? 'grid' : 'single'}`}>
      {shown.map((s, i) => (
        <StatTile key={s.name + i} series={s} opts={opts} spec={spec} timeRange={timeRange} showName={shown.length > 1} theme={theme} />
      ))}
    </div>
  )
}

interface TileProps {
  series: SeriesValue
  opts: StatOptions
  spec: PanelSpec
  timeRange: { from: number; to: number } | null
  showName: boolean
  theme: Theme
}

function StatTile({ series, opts, spec, timeRange, showName, theme }: TileProps) {
  // Without thresholds a colour would only imply a judgement we haven't made.
  const neutral = opts.colorMode === 'none' || opts.thresholds.length === 0
  const color = neutral ? 'var(--fg)' : thresholdColor(series.value, opts.thresholds, theme)
  const filled = opts.colorMode === 'background'
  const ink = theme === 'light' ? '#ffffff' : '#0b0e14'
  const sparkColor = filled ? (theme === 'light' ? 'rgba(255,255,255,0.45)' : 'rgba(11,14,20,0.35)') : neutral ? CHART_THEMES[theme].series[0] : color
  const value =
    series.value !== null && opts.decimals !== null ? Number(series.value.toFixed(opts.decimals)) : series.value

  return (
    <div className="stat__tile" style={{ background: filled ? color : undefined }}>
      {opts.graph && series.points.length > 1 && (
        <Sparkline points={series.points} color={sparkColor} timeRange={timeRange} />
      )}
      <div className="stat__content">
        {showName && (
          <span className="stat__name mono" style={{ color: filled ? ink : undefined }}>
            {series.name}
          </span>
        )}
        <span className="stat__value" style={{ color: filled ? ink : color }}>
          {formatValue(value, spec.unit)}
        </span>
      </div>
    </div>
  )
}

interface SparklineProps {
  points: [number, number | null][]
  color: string
  timeRange: { from: number; to: number } | null
}

function Sparkline({ points, color, timeRange }: SparklineProps) {
  const option = useMemo<ChartOption>(
    () => ({
      animation: false,
      color: [color],
      grid: { left: 0, right: 0, top: 0, bottom: 0 },
      xAxis: { type: 'time', show: false, min: timeRange?.from, max: timeRange?.to },
      yAxis: { type: 'value', show: false, scale: true },
      tooltip: { show: false },
      series: [
        {
          type: 'line',
          data: points,
          showSymbol: false,
          lineStyle: { width: 1.5 },
          areaStyle: { opacity: 0.18 },
          connectNulls: false,
          silent: true,
        },
      ],
    }),
    [points, color, timeRange],
  )
  const ref = useECharts(option)
  return <div ref={ref} className="stat__spark" aria-hidden="true" />
}
