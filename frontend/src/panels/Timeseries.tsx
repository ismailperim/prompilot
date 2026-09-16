import { useMemo } from 'react'
import { buildTimeseriesOption } from './timeseriesOption'
import type { PanelRendererProps } from './types'
import { useECharts } from './useECharts'

export function Timeseries({ spec, frames, timeRange }: PanelRendererProps) {
  const option = useMemo(() => buildTimeseriesOption(spec, frames, timeRange), [spec, frames, timeRange])
  const ref = useECharts(option)
  const empty = frames.every((f) => f.fields.filter((x) => x.type === 'number').length === 0)

  return (
    <div className="chart-host">
      <div ref={ref} className="chart-host__canvas" />
      {empty && (
        <div className="panel-message panel-message--overlay">
          <strong>No data</strong>
          <span>The query returned no series for this time range.</span>
        </div>
      )}
    </div>
  )
}
