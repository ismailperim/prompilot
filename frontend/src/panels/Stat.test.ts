import { thresholdColor } from './statOptions'

describe('thresholdColor', () => {
  const t = [
    { value: 90, color: 'red' as const },
    { value: 70, color: 'orange' as const },
  ]
  it('applies the highest threshold at or below the value', () => {
    expect(thresholdColor(50, t)).toBe('#3fb950')
    expect(thresholdColor(70, t)).toBe('#f0883e')
    expect(thresholdColor(95, t)).toBe('#f47067')
    expect(thresholdColor(null, t)).toBe('#3fb950')
  })
})
