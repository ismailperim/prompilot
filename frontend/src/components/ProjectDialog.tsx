import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { GrafanaDatasource, Project, ProjectSource } from '../api/types'
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

const SOURCES: { value: ProjectSource; label: string }[] = [
  { value: 'prometheus', label: 'Prometheus' },
  { value: 'grafana', label: 'Through Grafana' },
]

function isHttpUrl(value: string): boolean {
  return /^https?:\/\/\S+/.test(value)
}

type LookupState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; datasources: GrafanaDatasource[] }
  | { kind: 'fail'; error: string }

type TestState = { kind: 'idle' } | { kind: 'testing' } | { kind: 'ok'; version: string | null } | { kind: 'fail'; error: string }

export function ProjectDialog({ project, onClose }: Props) {
  const reloadProjects = useDashboard((s) => s.reloadProjects)
  const selectProject = useDashboard((s) => s.selectProject)
  const projects = useDashboard((s) => s.projects)
  const current = useDashboard((s) => s.project)

  const [name, setName] = useState(project?.name ?? '')
  const [source, setSource] = useState<ProjectSource>(project?.source ?? 'prometheus')
  const [url, setUrl] = useState(project?.prometheusUrl || 'http://')
  const [grafanaUrl, setGrafanaUrl] = useState(project?.grafanaUrl ?? 'https://')
  const [datasourceUid, setDatasourceUid] = useState(project?.grafanaDatasourceUid ?? '')
  const [lookup, setLookup] = useState<LookupState>({ kind: 'idle' })
  const [username, setUsername] = useState(project?.prometheusUsername ?? '')
  const [password, setPassword] = useState('')
  const [clearPassword, setClearPassword] = useState(false)
  const [tlsVerify, setTlsVerify] = useState(project?.tlsVerify ?? true)
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

  const viaGrafana = source === 'grafana'
  const activeUrl = (viaGrafana ? grafanaUrl : url).trim()
  const complete = isHttpUrl(activeUrl) && (!viaGrafana || datasourceUid.trim() !== '')

  const connection = () => ({
    source,
    ...(viaGrafana
      ? { grafanaUrl: grafanaUrl.trim(), grafanaDatasourceUid: datasourceUid.trim() }
      : { prometheusUrl: url.trim() }),
    prometheusUsername: username.trim() || null,
    // On edit, an empty password field means "keep the stored one".
    prometheusPassword: password || null,
    tlsVerify,
  })

  async function findDatasources() {
    setLookup({ kind: 'loading' })
    try {
      const result = await api.projects.grafanaDatasources({
        grafanaUrl: grafanaUrl.trim(),
        prometheusUsername: username.trim() || null,
        prometheusPassword: password || null,
        tlsVerify,
        ...(project && !clearPassword ? { slug: project.slug } : {}),
      })
      if (!result.ok) {
        setLookup({ kind: 'fail', error: result.error ?? 'Failed' })
        return
      }
      setLookup({ kind: 'ok', datasources: result.datasources })
      const first = result.datasources[0]
      if (first && !result.datasources.some((d) => d.uid === datasourceUid)) setDatasourceUid(first.uid)
    } catch (e) {
      setLookup({ kind: 'fail', error: e instanceof Error ? e.message : String(e) })
    }
  }

  async function runTest() {
    setTest({ kind: 'testing' })
    try {
      const result = await api.projects.test({ ...connection(), ...(project && !clearPassword ? { slug: project.slug } : {}) })
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
          ...connection(),
          ...(clearPassword ? { clearPassword: true } : {}),
          tlsVerify,
        })
        await reloadProjects()
        if (project.slug === current) await selectProject(project.slug)
      } else {
        const created = await api.projects.create({ name: name.trim(), ...connection() })
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
        <div className="field">
          <span id="project-source-label">Connect</span>
          <div className="segmented segmented--fit" role="radiogroup" aria-labelledby="project-source-label">
            {SOURCES.map((s) => (
              <button
                key={s.value}
                type="button"
                role="radio"
                aria-checked={source === s.value}
                className={`segmented__item ${source === s.value ? 'is-active' : ''}`}
                onClick={() => {
                  setSource(s.value)
                  setTest({ kind: 'idle' })
                }}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
        {viaGrafana ? (
          <>
            <label className="field">
              <span>Grafana URL</span>
              <input className="mono" value={grafanaUrl} onChange={(e) => setGrafanaUrl(e.target.value)} placeholder="https://grafana.example.com" required spellCheck={false} />
            </label>
            <p className="hint">Queries run through Grafana&apos;s datasource proxy, as the user below. Viewer access to the datasource is enough.</p>
          </>
        ) : (
          <label className="field">
            <span>Prometheus URL</span>
            <input className="mono" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://prometheus:9090" required spellCheck={false} />
          </label>
        )}
        {!project && !viaGrafana && (
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
        {viaGrafana && (
          <div className="field">
            <span>Prometheus datasource</span>
            <div className="field-inline">
              {lookup.kind === 'ok' && lookup.datasources.length > 0 ? (
                <select value={datasourceUid} onChange={(e) => setDatasourceUid(e.target.value)} aria-label="Prometheus datasource">
                  {!lookup.datasources.some((d) => d.uid === datasourceUid) && datasourceUid && <option value={datasourceUid}>{datasourceUid}</option>}
                  {lookup.datasources.map((d) => (
                    <option key={d.uid} value={d.uid}>
                      {d.name}
                      {d.isDefault ? ' (default)' : ''} — {d.uid}
                    </option>
                  ))}
                </select>
              ) : (
                <input className="mono" value={datasourceUid} onChange={(e) => setDatasourceUid(e.target.value)} placeholder="datasource UID" spellCheck={false} aria-label="Datasource UID" />
              )}
              <button type="button" className="btn btn--sm" onClick={() => void findDatasources()} disabled={lookup.kind === 'loading' || !isHttpUrl(grafanaUrl.trim())}>
                {lookup.kind === 'loading' ? 'Loading…' : 'Find datasources'}
              </button>
            </div>
            {lookup.kind === 'ok' && lookup.datasources.length === 0 && <p className="modal__test-fail">No Prometheus datasources visible to this user.</p>}
            {lookup.kind === 'fail' && <p className="modal__test-fail">{lookup.error}</p>}
          </div>
        )}
        {project?.hasPassword && (
          <label className="check">
            <input type="checkbox" checked={clearPassword} onChange={(e) => setClearPassword(e.target.checked)} />
            Remove the stored password
          </label>
        )}
        {activeUrl.startsWith('https://') && (
          <label className="check">
            <input type="checkbox" checked={tlsVerify} onChange={(e) => setTlsVerify(e.target.checked)} />
            Verify the TLS certificate
            <span className="check__hint">Turn off for self-signed certificates, or mount a CA and set PROMETHEUS_CA_FILE.</span>
          </label>
        )}

        <div className="modal__test">
          <button type="button" className="btn btn--sm" onClick={runTest} disabled={test.kind === 'testing' || !complete}>
            {test.kind === 'testing' ? 'Testing…' : 'Test connection'}
          </button>
          {test.kind === 'ok' && (
            <span className="modal__test-ok">
              Connected{test.version ? ` — Prometheus ${test.version}` : ''}
              {viaGrafana ? ' via Grafana' : ''}
            </span>
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
          <button type="submit" className="btn btn--primary" disabled={busy || !name.trim() || !complete}>
            {busy ? 'Saving…' : project ? 'Save changes' : 'Create project'}
          </button>
        </div>
      </form>
    </div>
  )
}
