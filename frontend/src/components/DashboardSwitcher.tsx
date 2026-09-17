import { Check, ChevronDown, Copy, Pencil, Plus, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { useDashboard } from '../store/dashboard'

type Mode = 'closed' | 'menu' | 'new' | 'rename' | 'copy' | 'delete'

/** Dashboard name in the top bar; opens a menu to switch, create, rename, copy or delete dashboards. */
export function DashboardSwitcher() {
  const dashboards = useDashboard((s) => s.dashboards)
  const current = useDashboard((s) => s.dashboardId)
  const dashboard = useDashboard((s) => s.dashboard)
  const selectDashboard = useDashboard((s) => s.selectDashboard)
  const createDashboard = useDashboard((s) => s.createDashboard)
  const renameDashboard = useDashboard((s) => s.renameDashboard)
  const deleteDashboard = useDashboard((s) => s.deleteDashboard)
  const [mode, setMode] = useState<Mode>('closed')
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (mode === 'closed') return
    const onPointerDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setMode('closed')
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMode('closed')
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [mode])

  const open = (next: Mode) => {
    setError(null)
    setTitle(next === 'rename' ? (dashboard?.title ?? '') : next === 'copy' ? `${dashboard?.title ?? 'Dashboard'} (copy)` : '')
    setMode(next)
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (mode === 'new') await createDashboard(title.trim())
      else if (mode === 'rename') await renameDashboard(title.trim())
      else if (mode === 'copy' && current) await createDashboard(title.trim(), current)
      else if (mode === 'delete' && current) await deleteDashboard(current)
      setMode('closed')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const name = dashboard?.title ?? dashboards.find((d) => d.id === current)?.title ?? 'Dashboard'

  return (
    <div className="switcher switcher--dashboard" ref={root}>
      <button className="switcher__button" onClick={() => setMode(mode === 'closed' ? 'menu' : 'closed')} aria-haspopup="menu" aria-expanded={mode !== 'closed'}>
        <span className="switcher__name">{name}</span>
        <ChevronDown size={14} />
      </button>

      {mode === 'menu' && (
        <div className="popover switcher__menu" role="menu">
          <ul className="switcher__list">
            {dashboards.map((d) => (
              <li key={d.id}>
                <button
                  role="menuitemradio"
                  aria-checked={d.id === current}
                  className="switcher__item"
                  onClick={() => {
                    setMode('closed')
                    if (d.id !== current) void selectDashboard(d.id)
                  }}
                >
                  <span className="switcher__check">{d.id === current && <Check size={13} />}</span>
                  <span className="switcher__label">
                    <span>{d.title}</span>
                    <span className="switcher__url mono">
                      {d.panels} {d.panels === 1 ? 'panel' : 'panels'}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <div className="switcher__actions">
            <button className="switcher__action" onClick={() => open('new')}>
              <Plus size={13} /> New dashboard
            </button>
            <button className="switcher__action" onClick={() => open('rename')}>
              <Pencil size={13} /> Rename
            </button>
            <button className="switcher__action" onClick={() => open('copy')}>
              <Copy size={13} /> Duplicate
            </button>
            {dashboards.length > 1 && (
              <button className="switcher__action modal__danger" onClick={() => open('delete')}>
                <Trash2 size={13} /> Delete
              </button>
            )}
          </div>
        </div>
      )}

      {(mode === 'new' || mode === 'rename' || mode === 'copy' || mode === 'delete') && (
        <form className="popover switcher__form" onSubmit={submit}>
          {mode === 'delete' ? (
            <p className="switcher__question">
              Delete <strong>{name}</strong> and its {dashboard?.panels.length ?? 0} panels?
            </p>
          ) : (
            <label className="field">
              <span>{mode === 'new' ? 'New dashboard' : mode === 'rename' ? 'Rename dashboard' : 'Duplicate as'}</span>
              <input value={title} onChange={(e) => setTitle(e.target.value)} autoFocus required maxLength={120} placeholder="Payments SLOs" />
            </label>
          )}
          {error && (
            <p className="form__error" role="alert">
              {error}
            </p>
          )}
          <div className="form__actions">
            <button type="submit" className={`btn btn--sm ${mode === 'delete' ? 'btn--danger' : 'btn--primary'}`} disabled={busy || (mode !== 'delete' && !title.trim())}>
              {busy ? '…' : mode === 'new' ? 'Create' : mode === 'rename' ? 'Rename' : mode === 'copy' ? 'Duplicate' : 'Delete'}
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setMode('closed')}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
