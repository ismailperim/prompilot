import { formatSeconds, formatShort, formatTime, formatValue } from './units'

describe('formatShort', () => {
  it.each([
    [0, '0'],
    [0.1234, '0.123'],
    [12.5, '12.5'],
    [999, '999'],
    [1000, '1k'],
    [1234, '1.23k'],
    [1_500_000, '1.5M'],
    [-2_000_000_000, '-2G'],
  ])('%p → %p', (input, expected) => {
    expect(formatShort(input)).toBe(expected)
  })
})

describe('formatSeconds', () => {
  it.each([
    [0, '0 s'],
    [0.0000005, '0.5 µs'],
    [0.25, '250 ms'],
    [1.5, '1.5 s'],
    [90, '1.5 min'],
    [7200, '2 h'],
    [172800, '2 d'],
  ])('%p → %p', (input, expected) => {
    expect(formatSeconds(input)).toBe(expected)
  })
})

describe('formatValue', () => {
  it('handles missing values', () => {
    expect(formatValue(null, 'short')).toBe('–')
    expect(formatValue(NaN, 'bytes')).toBe('–')
  })

  it.each([
    [0.4567, 'percentunit', '45.7%'],
    [45.67, 'percent', '45.7%'],
    [1536, 'bytes', '1.5 KiB'],
    [1_500_000, 'decbytes', '1.5 MB'],
    [0, 'bytes', '0 B'],
    [2048, 'Bps', '2.05 kB/s'],
    [1_000_000, 'bps', '1 Mb/s'],
    [0.002, 'ms', '2 µs'],
    [2500, 'ms', '2.5 s'],
    [12345, 'reqps', '12.35k req/s'],
    [3, 'none', '3'],
  ] as const)('%p %s → %p', (value, unit, expected) => {
    expect(formatValue(value, unit)).toBe(expected)
  })
})

describe('formatTime', () => {
  const t = new Date(2024, 2, 13, 14, 5, 9).getTime()
  it('adapts granularity to the span', () => {
    expect(formatTime(t, 60_000)).toBe('14:05:09')
    expect(formatTime(t, 3_600_000)).toBe('14:05')
    expect(formatTime(t, 2 * 86_400_000)).toBe('03-13 14:05')
    expect(formatTime(t, 30 * 86_400_000)).toBe('03-13')
  })
})
