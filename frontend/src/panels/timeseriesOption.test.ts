import type { DataFrame, PanelSpec } from '../api/types'
import { buildTimeseriesOption, readOptions, seriesFromFrames } from './timeseriesOption'

const spec: PanelSpec = {
  version: 1,
  id: 'p1',
  type: 'timeseries',
  title: 'CPU',
  description: '',
  queries: [{ refId: 'A', expr: 'up', legend: null, instant: false }],
  unit: 'percentunit',
  timeFrom: null,
  options: {},
}

const wide: DataFrame = {
  refId: 'A',
  fields: [
    { name: 'time', type: 'time', values: [1000, 2000, 3000] },
    { name: 'cpu 0', type: 'number', values: [0.1, null, 0.3] },
    { name: 'cpu 1', type: 'number', values: [0.5, 0.6, 0.7] },
  ],
}

describe('readOptions', () => {
  it('applies defaults for missing options', () => {
    expect(readOptions(spec)).toEqual({
      draw: 'line',
      stack: false,
      fill: 0,
      lineWidth: 1,
      legend: 'bottom',
      min: null,
      max: null,
    })
  })
})

describe('seriesFromFrames', () => {
  it('turns a wide frame into one series per numeric field', () => {
    const series = seriesFromFrames([wide])
    expect(series.map((s) => s.name)).toEqual(['cpu 0', 'cpu 1'])
    expect(series[0].points).toEqual([
      [1000, 0.1],
      [2000, null],
      [3000, 0.3],
    ])
  })

  it('names single-value frames after their refId when several queries are present', () => {
    const a: DataFrame = {
      refId: 'A',
      fields: [
        { name: 'time', type: 'time', values: [1] },
        { name: 'value', type: 'number', values: [1] },
      ],
    }
    const b: DataFrame = { ...a, refId: 'B' }
    expect(seriesFromFrames([a, b]).map((s) => s.name)).toEqual(['A', 'B'])
  })

  it('ignores frames without a time field and non-numeric fields', () => {
    const table: DataFrame = {
      refId: 'A',
      fields: [
        { name: 'job', type: 'string', values: ['x'] },
        { name: 'value', type: 'number', values: [1] },
      ],
    }
    expect(seriesFromFrames([table])).toEqual([])
  })
})

describe('buildTimeseriesOption', () => {
  it('maps draw styles and stacking', () => {
    const bars = buildTimeseriesOption({ ...spec, options: { draw: 'bars', stack: true } }, [wide], null)
    const series = bars.series as { type: string; stack?: string }[]
    expect(series[0].type).toBe('bar')
    expect(series[0].stack).toBe('total')

    const points = buildTimeseriesOption({ ...spec, options: { draw: 'points' } }, [wide], null)
    expect((points.series as { type: string }[])[0].type).toBe('scatter')
  })

  it('pins the x axis to the requested range and hides the legend when asked', () => {
    const option = buildTimeseriesOption({ ...spec, options: { legend: 'hidden' } }, [wide], { from: 0, to: 5000 })
    expect((option.xAxis as { min: number; max: number }).min).toBe(0)
    expect((option.xAxis as { min: number; max: number }).max).toBe(5000)
    expect((option.legend as { show: boolean }).show).toBe(false)
  })

  it('formats y axis labels with the panel unit', () => {
    const option = buildTimeseriesOption(spec, [wide], null)
    const formatter = (option.yAxis as { axisLabel: { formatter: (v: number) => string } }).axisLabel.formatter
    expect(formatter(0.25)).toBe('25%')
  })
})
