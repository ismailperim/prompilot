import { Check, ChevronDown, Pencil, Plus } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useDashboard } from '../store/dashboard'
import { ProjectDialog } from './ProjectDialog'

/** Project name in the top bar; opens a menu to switch, edit or create projects. */
export function ProjectSwitcher() {
  const projects = useDashboard((s) => s.projects)
  const current = useDashboard((s) => s.project)
  const selectProject = useDashboard((s) => s.selectProject)
  const [open, setOpen] = useState(false)
  const [dialog, setDialog] = useState<'closed' | 'new' | 'edit'>('closed')
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const active = projects.find((p) => p.slug === current)

  return (
    <div className="switcher" ref={root}>
      <button className="switcher__button" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}>
        <span className="switcher__name">{active?.name ?? 'No project'}</span>
        <ChevronDown size={14} />
      </button>

      {open && (
        <div className="popover switcher__menu" role="menu">
          <ul className="switcher__list">
            {projects.map((p) => (
              <li key={p.slug}>
                <button
                  role="menuitemradio"
                  aria-checked={p.slug === current}
                  className="switcher__item"
                  onClick={() => {
                    setOpen(false)
                    if (p.slug !== current) void selectProject(p.slug)
                  }}
                >
                  <span className="switcher__check">{p.slug === current && <Check size={13} />}</span>
                  <span className="switcher__label">
                    <span>{p.name}</span>
                    <span className="switcher__url mono">{p.prometheusUrl}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <div className="switcher__actions">
            {active && (
              <button
                className="switcher__action"
                onClick={() => {
                  setOpen(false)
                  setDialog('edit')
                }}
              >
                <Pencil size={13} /> Edit “{active.name}”
              </button>
            )}
            <button
              className="switcher__action"
              onClick={() => {
                setOpen(false)
                setDialog('new')
              }}
            >
              <Plus size={13} /> New project
            </button>
          </div>
        </div>
      )}

      {dialog !== 'closed' && <ProjectDialog project={dialog === 'edit' ? active ?? null : null} onClose={() => setDialog('closed')} />}
    </div>
  )
}
