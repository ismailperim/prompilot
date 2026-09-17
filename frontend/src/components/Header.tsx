import { Download, Moon, RefreshCw, Sun } from 'lucide-react'
import type { Dashboard, SystemStatus } from '../api/types'
import { useDashboard } from '../store/dashboard'
import { useTheme } from '../theme'
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
  const theme = useTheme((s) => s.theme)
  const toggleTheme = useTheme((s) => s.toggle)
  const canExport = dashboard.panels.length > 0

  return (
    <header className="topbar">
      <div className="brand">
        <LogoMark size={22} />
        <Wordmark />
        <span className="brand__dashboard" title={dashboard.title}>
          {dashboard.title}
        </span>
      </div>

      <TimeRangePicker value={dashboard.timeRange} resolved={resolvedRange} onChange={(r) => void setTimeRange(r)} />

      <div className="topbar__right">
        <div className="conn" aria-label="Connections">
          <span className={`conn__item ${status?.prometheus.reachable ? 'is-ok' : 'is-err'}`} title={status?.prometheus.url ?? 'Prometheus'}>
            <span className="conn__dot" />
            prometheus
          </span>
          {status?.llm.enabled && (
            <span className="conn__item is-ok" title="Chat model">
              <span className="conn__dot" />
              {status.llm.model}
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

        <button className="btn btn--icon btn--ghost" onClick={() => void refresh()} disabled={refreshing} aria-label="Refresh now" title="Refresh now">
          <RefreshCw size={15} className={refreshing ? 'spin' : ''} />
        </button>

        <button className="btn btn--icon btn--ghost" onClick={toggleTheme} aria-label={theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme'} title="Theme">
          {theme === 'light' ? <Moon size={15} /> : <Sun size={15} />}
        </button>

        <a
          className={`btn ${canExport ? '' : 'btn--disabled'}`}
          href="/api/export/grafana"
          download
          aria-disabled={!canExport}
          title="Download as a Grafana dashboard (Dashboards → New → Import)"
        >
          <Download size={14} />
          Export to Grafana
        </a>
      </div>
    </header>
  )
}
