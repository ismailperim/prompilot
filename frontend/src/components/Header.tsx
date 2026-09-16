import { Download, RefreshCw } from 'lucide-react'
import type { Dashboard, SystemStatus } from '../api/types'
import { useDashboard } from '../store/dashboard'
import { LogoMark, Wordmark } from './Logo'
import { TimeRangePicker } from './TimeRangePicker'

const REFRESH_OPTIONS = [
  { value: '', label: 'Off' },
  { value: '10s', label: '10s' },
  { value: '30s', label: '30s' },
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
]

export function Header({ dashboard, status }: { dashboard: Dashboard; status: SystemStatus | null }) {
  const resolvedRange = useDashboard((s) => s.resolvedRange)
  const refreshing = useDashboard((s) => s.refreshing)
  const setTimeRange = useDashboard((s) => s.setTimeRange)
  const setRefreshInterval = useDashboard((s) => s.setRefreshInterval)
  const refresh = useDashboard((s) => s.refresh)
  const canExport = dashboard.panels.length > 0

  return (
    <header className="topbar">
      <div className="brand">
        <LogoMark size={26} />
        <Wordmark />
        <span className="brand__sep" aria-hidden="true" />
        <span className="brand__dashboard" title={dashboard.title}>
          {dashboard.title}
        </span>
      </div>

      <TimeRangePicker value={dashboard.timeRange} resolved={resolvedRange} onChange={(r) => void setTimeRange(r)} />

      <div className="topbar__right">
        <div className="status-chips" aria-label="Connections">
          <span
            className={`status-chip ${status?.prometheus.reachable ? 'status-chip--ok' : 'status-chip--err'}`}
            title={status?.prometheus.url ?? 'Prometheus'}
          >
            <span className="status-chip__dot" />
            Prometheus
          </span>
          {status?.llm.enabled && (
            <span className="status-chip status-chip--ok" title="Chat model">
              <span className="status-chip__dot" />
              <span className="mono">{status.llm.model}</span>
            </span>
          )}
        </div>

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

        <button className="btn btn--icon" onClick={() => void refresh()} disabled={refreshing} aria-label="Refresh now" title="Refresh now">
          <RefreshCw size={16} className={refreshing ? 'spin' : ''} />
        </button>

        <a
          className={`btn ${canExport ? '' : 'btn--disabled'}`}
          href="/api/export/grafana"
          download
          aria-disabled={!canExport}
          title="Download as a Grafana dashboard (Dashboards → New → Import)"
        >
          <Download size={16} />
          Export to Grafana
        </a>
      </div>
    </header>
  )
}
