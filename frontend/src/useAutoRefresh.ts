import { useEffect } from 'react'
import { useDashboard } from './store/dashboard'

const UNITS_MS: Record<string, number> = { ms: 1, s: 1000, m: 60_000, h: 3_600_000, d: 86_400_000, w: 604_800_000 }

export function parseDurationMs(value: string | null): number | null {
  if (!value) return null
  const match = /^(\d+)(ms|s|m|h|d|w)$/.exec(value.trim())
  if (!match) return null
  return Number(match[1]) * UNITS_MS[match[2]]
}

/** Re-fetch panel data on the dashboard's refresh interval; pauses while the tab is hidden. */
export function useAutoRefresh(refresh: string | null) {
  const doRefresh = useDashboard((s) => s.refresh)
  const interval = parseDurationMs(refresh)

  useEffect(() => {
    if (!interval) return
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') void doRefresh()
    }, Math.max(interval, 1000))
    return () => window.clearInterval(id)
  }, [interval, doRefresh])
}
