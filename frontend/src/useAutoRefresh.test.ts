import { parseDurationMs } from './useAutoRefresh'

describe('parseDurationMs', () => {
  it.each([
    ['10s', 10_000],
    ['1m', 60_000],
    ['2h', 7_200_000],
    ['500ms', 500],
  ])('%s → %d', (input, expected) => {
    expect(parseDurationMs(input)).toBe(expected)
  })

  it('returns null for off/invalid', () => {
    expect(parseDurationMs(null)).toBeNull()
    expect(parseDurationMs('')).toBeNull()
    expect(parseDurationMs('soon')).toBeNull()
  })
})
