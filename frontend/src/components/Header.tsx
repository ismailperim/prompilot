import { Download, LogOut, Maximize2, Minimize2, Moon, PanelRightClose, PanelRightOpen, RefreshCw, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { Dashboard, SystemStatus } from '../api/types'
import { api } from '../api/client'
import { currentApi, useDashboard } from '../store/dashboard'
import { DashboardSwitcher } from './DashboardSwitcher'
import { ProjectSwitcher } from './ProjectSwitcher'
import { useLayout, useTheme } from '../theme'
import { LogoMark, Wordmark } from './Logo'
import { TimeRangePicker } from './TimeRangePicker'

const REPO_URL = 'https://github.com/ismailperim/prompilot'

/** GitHub's mark; lucide dropped brand icons, so it lives here. */
function GitHubMark({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  )
}

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
  const sidebarOpen = useLayout((s) => s.sidebarOpen)
  const toggleSidebar = useLayout((s) => s.toggleSidebar)
  const setSidebarOpen = useLayout((s) => s.setSidebarOpen)
  const [fullscreen, setFullscreen] = useState(Boolean(document.fullscreenElement))
  const canExport = dashboard.panels.length > 0
  const authEnabled = useDashboard((s) => s.authEnabled)

  useEffect(() => {
    const onChange = () => setFullscreen(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  // Full screen = the dashboard alone: hide the sidebar and let the browser take the screen.
  const toggleFullscreen = () => {
    if (document.fullscreenElement) {
      void document.exitFullscreen()
    } else {
      setSidebarOpen(false)
      void document.documentElement.requestFullscreen?.()
    }
  }

  return (
    <header className="topbar">
      <div className="brand">
        <LogoMark size={22} />
        <Wordmark />
        <ProjectSwitcher />
        <DashboardSwitcher />
      </div>

      <TimeRangePicker value={dashboard.timeRange} resolved={resolvedRange} onChange={(r) => void setTimeRange(r)} />

      <div className="topbar__right">
        <div className="conn" aria-label="Connections">
          <span className={`conn__item ${status?.prometheus.reachable ? 'is-ok' : 'is-err'}`} title={status?.prometheus.url ?? 'Prometheus'}>
            <span className="conn__dot" />
            prometheus
          </span>
          {status?.llm.enabled && (
            <span className="conn__item conn__item--model is-ok" title="Chat model">
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

        <button
          className="btn btn--icon btn--ghost"
          onClick={toggleSidebar}
          aria-label={sidebarOpen ? 'Hide the side panel' : 'Show the side panel'}
          title={sidebarOpen ? 'Hide side panel' : 'Show side panel'}
        >
          {sidebarOpen ? <PanelRightClose size={15} /> : <PanelRightOpen size={15} />}
        </button>

        <button className="btn btn--icon btn--ghost" onClick={toggleFullscreen} aria-label={fullscreen ? 'Exit full screen' : 'Full screen'} title={fullscreen ? 'Exit full screen' : 'Full screen'}>
          {fullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
        </button>

        <button className="btn btn--icon btn--ghost" onClick={toggleTheme} aria-label={theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme'} title="Theme">
          {theme === 'light' ? <Moon size={15} /> : <Sun size={15} />}
        </button>

        <a className="btn btn--icon btn--ghost" href={REPO_URL} target="_blank" rel="noreferrer" aria-label="PromPilot on GitHub" title="Source, issues and releases on GitHub">
          <GitHubMark size={15} />
        </a>

        <a
          className={`btn ${canExport ? '' : 'btn--disabled'}`}
          href={currentApi().exportUrl}
          download
          aria-disabled={!canExport}
          title="Download as a Grafana dashboard (Dashboards → New → Import)"
        >
          <Download size={14} />
          <span className="topbar__export-label">Export to Grafana</span>
        </a>

        {authEnabled && (
          <button
            className="btn btn--icon btn--ghost"
            onClick={() => void api.auth.logout().then(() => window.location.reload())}
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut size={15} />
          </button>
        )}
      </div>
    </header>
  )
}
