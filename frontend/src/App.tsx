import { useEffect, useState } from 'react'
import { UNAUTHORIZED_EVENT, api } from './api/client'
import { CatalogBanner } from './components/CatalogBanner'
import { Login } from './components/Login'
import { LogoMark, Wordmark } from './components/Logo'
import { ProjectDialog } from './components/ProjectDialog'
import { Header } from './components/Header'
import { StatusBanner } from './components/StatusBanner'
import { VoiceOrb } from './chat/VoiceOrb'
import { loadVoiceCapabilities } from './chat/voice'
import { DashboardGrid } from './grid/DashboardGrid'
import { Sidebar, type SidebarTab } from './sidebar/Sidebar'
import { slugFromLocation, useDashboard } from './store/dashboard'
import { useLayout } from './theme'
import { useAutoRefresh } from './useAutoRefresh'
import './app.css'

type Gate = 'checking' | 'locked' | 'open'

export default function App() {
  const [gate, setGate] = useState<Gate>('checking')
  const dashboard = useDashboard((s) => s.dashboard)
  const status = useDashboard((s) => s.status)
  const loading = useDashboard((s) => s.loading)
  const error = useDashboard((s) => s.error)
  const catalog = useDashboard((s) => s.catalog)
  const load = useDashboard((s) => s.load)
  const project = useDashboard((s) => s.project)
  const projects = useDashboard((s) => s.projects)
  const selectProject = useDashboard((s) => s.selectProject)
  const [creating, setCreating] = useState(false)
  const loadCatalogStatus = useDashboard((s) => s.loadCatalogStatus)
  const rebuildCatalog = useDashboard((s) => s.rebuildCatalog)
  const addPanel = useDashboard((s) => s.addPanel)
  const patchPanel = useDashboard((s) => s.patchPanel)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [tab, setTab] = useState<SidebarTab | null>(null)
  const sidebarOpen = useLayout((s) => s.sidebarOpen)
  const setSidebarOpen = useLayout((s) => s.setSidebarOpen)

  // Sign-in gate: ask once, then react to any 401 the API sends later (expired session).
  useEffect(() => {
    api.auth
      .status()
      .then((a) => setGate(a.authenticated ? 'open' : 'locked'))
      .catch(() => setGate('open'))
    const onUnauthorized = () => setGate('locked')
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [])

  useEffect(() => {
    if (gate !== 'open') return
    void loadVoiceCapabilities().then(() => load())
  }, [gate, load])

  // Browser back/forward between /p/<slug> addresses.
  useEffect(() => {
    const onPop = () => {
      const slug = slugFromLocation()
      if (slug && slug !== useDashboard.getState().project) void selectProject(slug)
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [selectProject])

  // While the catalog builds, poll its status so the banner and browser update.
  const building = catalog?.state === 'building'
  useEffect(() => {
    if (!building) return
    const id = window.setInterval(() => void loadCatalogStatus(), 2000)
    return () => window.clearInterval(id)
  }, [building, loadCatalogStatus])

  useAutoRefresh(dashboard?.refresh ?? null)

  const editing = dashboard?.panels.find((p) => p.spec.id === editingId)?.spec ?? null
  const openTab = (next: SidebarTab) => {
    setTab(next)
    setSidebarOpen(true)
  }

  if (gate === 'locked') {
    return <Login onSuccess={() => setGate('open')} />
  }

  if (gate === 'checking' || (loading && !dashboard)) {
    return (
      <main className="app app--centered">
        <p className="muted">Loading…</p>
      </main>
    )
  }

  if (!project && !error) {
    return (
      <main className="app app--centered">
        <div className="card card--dialog">
          <div className="brand">
            <LogoMark size={22} />
            <Wordmark />
          </div>
          <h2 className="card__title">Connect your first Prometheus</h2>
          <p className="muted">
            {projects.length === 0
              ? 'No projects yet. Each project is one Prometheus source with its own dashboard, catalog and notes.'
              : 'Pick a project to continue.'}
          </p>
          <button className="btn btn--primary" onClick={() => setCreating(true)}>
            New project
          </button>
        </div>
        {creating && <ProjectDialog project={null} onClose={() => setCreating(false)} />}
      </main>
    )
  }

  if (!dashboard) {
    return (
      <main className="app app--centered">
        <div className="card card--dialog">
          <h2 className="card__title">Can't reach the PromPilot backend</h2>
          <p className="muted">{error}</p>
          <button className="btn btn--primary" onClick={() => void load()}>
            Try again
          </button>
        </div>
      </main>
    )
  }

  return (
    <div className="app">
      <Header dashboard={dashboard} status={status} />
      <StatusBanner status={status} error={error} />
      <CatalogBanner status={catalog} onRebuild={() => void rebuildCatalog()} />
      <div className={`workspace ${sidebarOpen ? 'workspace--sidebar' : ''}`}>
        <main className="workspace__main workspace__main--with-orb">
          {dashboard.panels.length === 0 ? (
            <div className="empty">
              <h2 className="empty__title">No panels yet</h2>
              <p className="empty__text">
                <button className="link" onClick={() => openTab('chat')}>
                  Ask for a chart
                </button>{' '}
                in plain language, <button className="link" onClick={() => openTab('metrics')}>browse</button> the{' '}
                {catalog?.metricCount ?? ''} metrics in the catalog, or{' '}
                <button className="link" onClick={() => openTab('build')}>
                  build one
                </button>{' '}
                from PromQL you already know.
              </p>
            </div>
          ) : (
            <DashboardGrid
              panels={dashboard.panels}
              onEdit={(id) => {
                setEditingId(id)
                setSidebarOpen(true)
              }}
            />
          )}
          <VoiceOrb />
        </main>
        {sidebarOpen && (
        <Sidebar
          status={status}
          catalog={catalog}
          editing={editing}
          tab={tab}
          onTab={setTab}
          onCancelEdit={() => setEditingId(null)}
          onRebuildCatalog={() => void rebuildCatalog()}
          onSubmit={async (spec) => {
            if (editing) {
              await patchPanel(editing.id, spec)
              setEditingId(null)
            } else {
              await addPanel(spec)
            }
          }}
        />
        )}
      </div>
    </div>
  )
}
