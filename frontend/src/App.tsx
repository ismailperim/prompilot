import { Database, MessageSquare, SlidersHorizontal } from 'lucide-react'
import { useEffect, useState } from 'react'
import { CatalogBanner } from './components/CatalogBanner'
import { Header } from './components/Header'
import { StatusBanner } from './components/StatusBanner'
import { DashboardGrid } from './grid/DashboardGrid'
import { Sidebar, type SidebarTab } from './sidebar/Sidebar'
import { useDashboard } from './store/dashboard'
import { useAutoRefresh } from './useAutoRefresh'
import './app.css'

export default function App() {
  const dashboard = useDashboard((s) => s.dashboard)
  const status = useDashboard((s) => s.status)
  const loading = useDashboard((s) => s.loading)
  const error = useDashboard((s) => s.error)
  const catalog = useDashboard((s) => s.catalog)
  const load = useDashboard((s) => s.load)
  const loadCatalogStatus = useDashboard((s) => s.loadCatalogStatus)
  const rebuildCatalog = useDashboard((s) => s.rebuildCatalog)
  const addPanel = useDashboard((s) => s.addPanel)
  const patchPanel = useDashboard((s) => s.patchPanel)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [tab, setTab] = useState<SidebarTab | null>(null)

  useEffect(() => {
    void load()
  }, [load])

  // While the catalog builds, poll its status so the banner and browser update.
  const building = catalog?.state === 'building'
  useEffect(() => {
    if (!building) return
    const id = window.setInterval(() => void loadCatalogStatus(), 2000)
    return () => window.clearInterval(id)
  }, [building, loadCatalogStatus])

  useAutoRefresh(dashboard?.refresh ?? null)

  const editing = dashboard?.panels.find((p) => p.spec.id === editingId)?.spec ?? null

  if (loading && !dashboard) {
    return (
      <main className="app app--centered">
        <p className="muted">Loading dashboard…</p>
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
      <div className="workspace">
        <main className="workspace__main">
          {dashboard.panels.length === 0 ? (
            <div className="empty">
              <div className="empty__intro">
                <h2 className="empty__title">No panels yet</h2>
                <p className="muted">Three ways to get the first one on the board.</p>
              </div>
              <div className="empty__paths">
                <button className="path" onClick={() => setTab('chat')}>
                  <span className="path__icon">
                    <MessageSquare size={18} />
                  </span>
                  <span className="path__title">Ask</span>
                  <span className="path__text">
                    “CPU per core as a percentage” — the assistant finds the metric, tests the PromQL and adds the panel.
                  </span>
                </button>
                <button className="path" onClick={() => setTab('metrics')}>
                  <span className="path__icon">
                    <Database size={18} />
                  </span>
                  <span className="path__title">Browse</span>
                  <span className="path__text">
                    Search the catalog of {catalog?.metricCount ?? 'your'} metrics and pick one; a sensible query is
                    pre-filled.
                  </span>
                </button>
                <button className="path" onClick={() => setTab('build')}>
                  <span className="path__icon">
                    <SlidersHorizontal size={18} />
                  </span>
                  <span className="path__title">Build</span>
                  <span className="path__text">
                    Know the PromQL already? Paste <code>rate(node_cpu_seconds_total[5m])</code> and pick a unit.
                  </span>
                </button>
              </div>
            </div>
          ) : (
            <DashboardGrid panels={dashboard.panels} onEdit={setEditingId} />
          )}
        </main>
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
      </div>
    </div>
  )
}
