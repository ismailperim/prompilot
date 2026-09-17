import { useMemo } from 'react'
import type { PanelSpec } from '../api/types'
import { formatValue } from '../format/units'
import { CHART_THEMES, useTheme, type Theme } from '../theme'
import { bands, readGaugeOptions, type GaugeOptions } from './gaugeOptions'
import { seriesValues, type SeriesValue } from './reduce'
import { CHART_FONT } from './timeseriesOption'
import type { PanelRendererProps } from './types'
import { useECharts, type ChartOption } from './useECharts'

export function Gauge({ spec, frames }: PanelRendererProps) {
  const theme = useTheme((s) => s.theme)
  const opts = readGaugeOptions(spec)
  const series = useMemo(() => seriesValues(frames, opts.reduce), [frames, opts.reduce])
  const shown = series.slice(0, 6)

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
        <Dial key={s.name + i} series={s} opts={opts} spec={spec} theme={theme} showName={shown.length > 1} />
      ))}
    </div>
  )
}

interface DialProps {
  series: SeriesValue
  opts: GaugeOptions
  spec: PanelSpec
  theme: Theme
  showName: boolean
}

function Dial({ series, opts, spec, theme, showName }: DialProps) {
  const t = CHART_THEMES[theme]
  const value = series.value
  const shownValue = value !== null && opts.decimals !== null ? Number(value.toFixed(opts.decimals)) : value
  const option = useMemo<ChartOption>(
    () => ({
      animation: false,
      series: [
        {
          type: 'gauge',
          min: opts.min,
          max: opts.max,
          startAngle: 205,
          endAngle: -25,
          radius: '100%',
          center: ['50%', '60%'],
          splitNumber: 4,
          axisLine: { lineStyle: { width: 10, color: bands(opts, theme) } },
          progress: { show: opts.thresholds.length === 0, width: 10, itemStyle: { color: t.series[0] } },
          pointer: { show: true, length: '55%', width: 4, itemStyle: { color: t.tooltipText } },
          axisTick: { show: false },
          splitLine: { show: opts.showThresholdMarkers, length: 4, lineStyle: { color: t.tooltipLine, width: 1 } },
          axisLabel: {
            show: true,
            distance: 8,
            color: t.text,
            fontSize: 11,
            fontFamily: CHART_FONT,
            formatter: (v: number) => formatValue(v, spec.unit),
          },
          anchor: { show: true, size: 8, itemStyle: { color: t.tooltipText } },
          title: { show: false },
          detail: {
            valueAnimation: false,
            offsetCenter: [0, '52%'],
            fontSize: 22,
            fontWeight: 500,
            fontFamily: CHART_FONT,
            color: t.tooltipText,
            formatter: () => formatValue(shownValue, spec.unit),
          },
          data: [{ value: value ?? opts.min }],
        },
      ],
    }),
    [opts, spec.unit, theme, t, value, shownValue],
  )
  const { ref } = useECharts(option)
  return (
    <div className="stat__tile gauge__tile">
      {showName && <span className="stat__name mono gauge__name">{series.name}</span>}
      <div ref={ref} className="gauge__canvas" />
    </div>
  )
}
