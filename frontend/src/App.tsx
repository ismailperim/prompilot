import { useEffect, useState } from 'react'
import { fetchHealth, type Health } from './api/client'

type Status = { kind: 'loading' } | { kind: 'ok'; health: Health } | { kind: 'error'; message: string }

export default function App() {
  const [status, setStatus] = useState<Status>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then((health) => setStatus({ kind: 'ok', health }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setStatus({ kind: 'error', message: error instanceof Error ? error.message : String(error) })
      })
    return () => controller.abort()
  }, [])

  return (
    <main style={{ padding: '2rem', maxWidth: 720, margin: '0 auto' }}>
      <h1 style={{ marginBottom: '0.25rem' }}>PromPilot</h1>
      <p style={{ color: 'var(--muted)', marginTop: 0 }}>
        Chat-driven Prometheus visualization with Grafana export.
      </p>
      <section aria-label="Backend status">
        {status.kind === 'loading' && <p>Connecting to backend…</p>}
        {status.kind === 'error' && (
          <p style={{ color: 'var(--err)' }}>Backend unreachable: {status.message}</p>
        )}
        {status.kind === 'ok' && (
          <dl>
            <dt>Backend</dt>
            <dd style={{ color: 'var(--ok)' }}>{status.health.status}</dd>
            <dt>Prometheus</dt>
            <dd>{status.health.prometheus_url}</dd>
            <dt>LLM</dt>
            <dd>{status.health.llm_enabled ? 'configured' : 'not configured'}</dd>
          </dl>
        )}
      </section>
    </main>
  )
}
