import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { useDashboard } from '../store/dashboard'
import { useTheme } from '../theme'
import { buildTimeseriesOption } from './timeseriesOption'
import type { PanelRendererProps } from './types'
import { useECharts } from './useECharts'

const MIN_DRAG_PX = 8

export function Timeseries({ spec, frames, timeRange }: PanelRendererProps) {
  const theme = useTheme((s) => s.theme)
  const option = useMemo(() => buildTimeseriesOption(spec, frames, timeRange, theme), [spec, frames, timeRange, theme])
  const { ref, chart } = useECharts(option)
  const setTimeRange = useDashboard((s) => s.setTimeRange)
  const empty = frames.every((f) => f.fields.filter((x) => x.type === 'number').length === 0)

  // Drag horizontally to zoom the whole dashboard to the selected span.
  const drag = useRef<{ startX: number } | null>(null)
  const [selection, setSelection] = useState<{ left: number; width: number } | null>(null)

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    const rect = e.currentTarget.getBoundingClientRect()
    drag.current = { startX: e.clientX - rect.left }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!drag.current) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width))
    const left = Math.min(drag.current.startX, x)
    setSelection({ left, width: Math.abs(x - drag.current.startX) })
  }
  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    const start = drag.current
    drag.current = null
    setSelection(null)
    if (!start || !chart.current) return
    const rect = e.currentTarget.getBoundingClientRect()
    const endX = Math.max(0, Math.min(e.clientX - rect.left, rect.width))
    if (Math.abs(endX - start.startX) < MIN_DRAG_PX) return
    const [a, b] = [start.startX, endX].sort((p, q) => p - q)
    const from = chart.current.convertFromPixel({ xAxisIndex: 0 }, a) as number
    const to = chart.current.convertFromPixel({ xAxisIndex: 0 }, b) as number
    if (!Number.isFinite(from) || !Number.isFinite(to) || to - from < 1000) return
    const iso = (ms: number) => new Date(Math.round(ms / 1000) * 1000).toISOString().replace('.000Z', 'Z')
    void setTimeRange({ from: iso(from), to: iso(to) })
  }

  return (
    <div className="chart-host" onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={() => { drag.current = null; setSelection(null) }} title="Drag to zoom">
      <div ref={ref} className="chart-host__canvas" />
      {selection && selection.width > 2 && <div className="chart-host__selection" style={{ left: selection.left, width: selection.width }} />}
      {empty && (
        <div className="panel-message panel-message--overlay">
          <strong>No data</strong>
          <span>The query returned no series for this time range.</span>
        </div>
      )}
    </div>
  )
}
