import type { Dashboard } from '../api/types'
import { useDashboard } from '../store/dashboard'
import { TimeRangePicker } from './TimeRangePicker'

const REFRESH_OPTIONS = [
  { value: '', label: 'Off' },
  { value: '10s', label: '10s' },
  { value: '30s', label: '30s' },
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
]

export function Header({ dashboard }: { dashboard: Dashboard }) {
  const resolvedRange = useDashboard((s) => s.resolvedRange)
  const refreshing = useDashboard((s) => s.refreshing)
  const setTimeRange = useDashboard((s) => s.setTimeRange)
  const setRefreshInterval = useDashboard((s) => s.setRefreshInterval)
  const refresh = useDashboard((s) => s.refresh)

  return (
    <header className="topbar">
      <div className="brand">
        <svg className="brand__mark" viewBox="0 0 32 32" aria-hidden="true">
          <polyline points="4,23 11,13 16,18 22,8 28,13" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="brand__name">PromPilot</span>
        <span className="brand__dashboard">{dashboard.title}</span>
      </div>

      <TimeRangePicker value={dashboard.timeRange} resolved={resolvedRange} onChange={(r) => void setTimeRange(r)} />

      <div className="topbar__controls">
        <label className="select">
          <span className="select__label">Refresh</span>
          <select value={dashboard.refresh ?? ''} onChange={(e) => void setRefreshInterval(e.target.value || null)}>
            {REFRESH_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <button className="btn btn--ghost" onClick={() => void refresh()} disabled={refreshing} aria-label="Refresh now">
          <span className={refreshing ? 'spin' : ''}>↻</span>
        </button>
        <a
          className={`btn ${dashboard.panels.length === 0 ? 'btn--disabled' : ''}`}
          href="/api/export/grafana"
          download
          aria-disabled={dashboard.panels.length === 0}
          title="Download as Grafana dashboard JSON (Dashboards → New → Import)"
        >
          Export to Grafana
        </a>
      </div>
    </header>
  )
}
