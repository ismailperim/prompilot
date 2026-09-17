import { bands } from './gaugeOptions'

describe('gauge bands', () => {
  it('maps thresholds to axis colour stops', () => {
    const b = bands({ min: 0, max: 100, reduce: 'last', decimals: null, showThresholdMarkers: true, thresholds: [{ value: 90, color: 'red' }, { value: 70, color: 'orange' }] }, 'light')
    expect(b).toEqual([
      [0.7, '#1a7f37'],
      [0.9, '#c8541a'],
      [1, '#cf222e'],
    ])
  })
  it('uses a neutral track without thresholds', () => {
    expect(bands({ min: 0, max: 1, reduce: 'last', decimals: null, showThresholdMarkers: true, thresholds: [] }, 'dark')).toEqual([[1, '#262930']])
  })
})
