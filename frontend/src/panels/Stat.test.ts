import { thresholdColor } from './statOptions'

describe('thresholdColor', () => {
  const t = [
    { value: 90, color: 'red' as const },
    { value: 70, color: 'orange' as const },
  ]
  it('applies the highest threshold at or below the value', () => {
    expect(thresholdColor(50, t)).toBe('#1a7f37')
    expect(thresholdColor(70, t)).toBe('#c8541a')
    expect(thresholdColor(95, t)).toBe('#cf222e')
    expect(thresholdColor(null, t)).toBe('#1a7f37')
    expect(thresholdColor(95, t, 'dark')).toBe('#f47067')
  })
})
