import { useEffect, useState } from 'react'
import { Header } from './components/Header'
import { StatusBanner } from './components/StatusBanner'
import { DashboardGrid } from './grid/DashboardGrid'
import { Sidebar } from './sidebar/Sidebar'
import { useDashboard } from './store/dashboard'
import { useAutoRefresh } from './useAutoRefresh'
import './app.css'

export default function App() {
  const dashboard = useDashboard((s) => s.dashboard)
  const status = useDashboard((s) => s.status)
  const loading = useDashboard((s) => s.loading)
  const error = useDashboard((s) => s.error)
  const load = useDashboard((s) => s.load)
  const addPanel = useDashboard((s) => s.addPanel)
  const patchPanel = useDashboard((s) => s.patchPanel)
  const [editingId, setEditingId] = useState<string | null>(null)

  useEffect(() => {
    void load()
  }, [load])

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
        <div className="card">
          <h2>Can't reach the PromPilot backend</h2>
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
      <Header dashboard={dashboard} />
      <StatusBanner status={status} error={error} />
      <div className="workspace">
        <main className="workspace__main">
          {dashboard.panels.length === 0 ? (
            <div className="empty">
              <h2>No panels yet</h2>
              <p className="muted">
                Add one from the form on the right — try <code>up</code> or{' '}
                <code>rate(node_cpu_seconds_total[5m])</code>.
              </p>
            </div>
          ) : (
            <DashboardGrid panels={dashboard.panels} onEdit={setEditingId} />
          )}
        </main>
        <Sidebar
          status={status}
          editing={editing}
          onCancelEdit={() => setEditingId(null)}
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
