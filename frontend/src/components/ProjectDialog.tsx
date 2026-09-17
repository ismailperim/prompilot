import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { Project } from '../api/types'
import { useDashboard } from '../store/dashboard'

interface Props {
  /** Existing project to edit, or null to create one. */
  project: Project | null
  onClose: () => void
}

const DEMO_SERVERS = [
  { label: 'demo.promlabs.com', url: 'https://demo.promlabs.com', name: 'PromLabs demo' },
  { label: 'prometheus.demo.prometheus.io', url: 'https://prometheus.demo.prometheus.io', name: 'Prometheus demo' },
]

type TestState = { kind: 'idle' } | { kind: 'testing' } | { kind: 'ok'; version: string | null } | { kind: 'fail'; error: string }

export function ProjectDialog({ project, onClose }: Props) {
  const reloadProjects = useDashboard((s) => s.reloadProjects)
  const selectProject = useDashboard((s) => s.selectProject)
  const projects = useDashboard((s) => s.projects)
  const current = useDashboard((s) => s.project)

  const [name, setName] = useState(project?.name ?? '')
  const [url, setUrl] = useState(project?.prometheusUrl ?? 'http://')
  const [username, setUsername] = useState(project?.prometheusUsername ?? '')
  const [password, setPassword] = useState('')
  const [clearPassword, setClearPassword] = useState(false)
  const [test, setTest] = useState<TestState>({ kind: 'idle' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const credentials = () => ({
    prometheusUrl: url.trim(),
    prometheusUsername: username.trim() || null,
    // On edit, an empty password field means "keep the stored one".
    prometheusPassword: password || null,
  })

  async function runTest() {
    setTest({ kind: 'testing' })
    try {
      const result = await api.projects.test(credentials())
      setTest(result.ok ? { kind: 'ok', version: result.version } : { kind: 'fail', error: result.error ?? 'Failed' })
    } catch (e) {
      setTest({ kind: 'fail', error: e instanceof Error ? e.message : String(e) })
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (project) {
        await api.projects.update(project.slug, {
          name: name.trim(),
          prometheusUrl: url.trim(),
          prometheusUsername: username.trim() || null,
          ...(password ? { prometheusPassword: password } : {}),
          ...(clearPassword ? { clearPassword: true } : {}),
        })
        await reloadProjects()
        if (project.slug === current) await selectProject(project.slug)
      } else {
        const created = await api.projects.create({ name: name.trim(), ...credentials() })
        await reloadProjects()
        await selectProject(created.slug)
      }
      onClose()
    } catch (e) {
      setError(e instanceof ApiError ? e.details.join('\n') || e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!project) return
    setBusy(true)
    try {
      await api.projects.remove(project.slug)
      await reloadProjects()
      const next = projects.find((p) => p.slug !== project.slug)
      if (next) await selectProject(next.slug)
      else window.location.assign('/')
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="project-dialog-title" onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="modal__panel" onSubmit={submit}>
        <h2 className="modal__title" id="project-dialog-title">
          {project ? 'Edit project' : 'New project'}
        </h2>
        <p className="modal__text">A project is one Prometheus source with its own dashboard, metric catalog and notes.</p>

        <label className="field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Production EU" required autoFocus />
        </label>
        <label className="field">
          <span>Prometheus URL</span>
          <input className="mono" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://prometheus:9090" required spellCheck={false} />
        </label>
        {!project && (
          <p className="hint">
            No Prometheus at hand? Try a public demo:{' '}
            {DEMO_SERVERS.map((d, i) => (
              <span key={d.url}>
                {i > 0 && ' · '}
                <button
                  type="button"
                  className="link"
                  onClick={() => {
                    setUrl(d.url)
                    if (!name.trim()) setName(d.name)
                  }}
                >
                  {d.label}
                </button>
              </span>
            ))}
          </p>
        )}
        <div className="field-row">
          <label className="field">
            <span>Username (optional)</span>
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" />
          </label>
          <label className="field">
            <span>Password (optional)</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={project?.hasPassword ? '•••••• (unchanged)' : ''}
              autoComplete="new-password"
            />
          </label>
        </div>
        {project?.hasPassword && (
          <label className="check">
            <input type="checkbox" checked={clearPassword} onChange={(e) => setClearPassword(e.target.checked)} />
            Remove the stored password
          </label>
        )}

        <div className="modal__test">
          <button type="button" className="btn btn--sm" onClick={runTest} disabled={test.kind === 'testing' || !url.trim()}>
            {test.kind === 'testing' ? 'Testing…' : 'Test connection'}
          </button>
          {test.kind === 'ok' && (
            <span className="modal__test-ok">Connected{test.version ? ` — Prometheus ${test.version}` : ''}</span>
          )}
          {test.kind === 'fail' && <span className="modal__test-fail">{test.error}</span>}
        </div>

        {error && (
          <p className="form__error" role="alert">
            {error}
          </p>
        )}

        <div className="modal__actions">
          {project && !confirmDelete && (
            <button type="button" className="btn btn--ghost btn--sm modal__danger" onClick={() => setConfirmDelete(true)} disabled={busy}>
              Delete project
            </button>
          )}
          {project && confirmDelete && (
            <span className="modal__confirm">
              Deletes its dashboard and catalog.{' '}
              <button type="button" className="btn btn--danger btn--sm" onClick={() => void remove()} disabled={busy}>
                Delete “{project.name}”
              </button>{' '}
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setConfirmDelete(false)}>
                Keep
              </button>
            </span>
          )}
          <span className="modal__spacer" />
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn btn--primary" disabled={busy || !name.trim() || !url.trim()}>
            {busy ? 'Saving…' : project ? 'Save changes' : 'Create project'}
          </button>
        </div>
      </form>
    </div>
  )
}
