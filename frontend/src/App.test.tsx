import { render, screen } from '@testing-library/react'
import App from './App'
import type { Dashboard, DataResponse } from './api/types'
import { initialState, useDashboard } from './store/dashboard'

const project = {
  slug: 'default',
  name: 'Default',
  prometheusUrl: 'http://prom:9090',
  prometheusUsername: null,
  hasPassword: false,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
}

const prometheusOk = { url: 'http://prom:9090', reachable: true, version: '3.5.0', error: null }
const instance = { llm: { enabled: false, model: null }, projects: 1, version: '0.1.0' }
const P = '/api/projects/default'

const emptyDashboard: Dashboard = {
  version: 1,
  title: 'Overview',
  timeRange: { from: 'now-1h', to: 'now' },
  refresh: '30s',
  panels: [],
}

const catalogReady = { state: 'ready', metricCount: 12, updatedAt: null, durationSeconds: 1, error: null, categories: { cpu: 12 } }

function mockApi(routes: Record<string, unknown>) {
  routes = {
    '/api/voice': { stt: 'browser', tts: 'browser' },
    '/api/status': instance,
    '/api/projects': [project],
    [`${P}/status`]: { project, prometheus: prometheusOk },
    [`${P}/catalog/status`]: catalogReady,
    [`${P}/knowledge`]: { directory: '/data/knowledge', promptLoaded: false, promptChars: 0, documents: [], chunks: 0, metricNotes: 0, playbooks: [], prompt: null, promptFromFiles: null },
    ...routes,
  }
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = typeof input === 'string' ? input : (input as Request).url
    const path = url.replace(/^https?:\/\/[^/]+/, '').replace(/\?.*$/, '')
    if (path in routes) {
      return new Response(JSON.stringify(routes[path]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    return new Response(JSON.stringify({ detail: `no route for ${path}` }), { status: 404 })
  })
}

describe('App', () => {
  beforeEach(() => useDashboard.setState(initialState))
  afterEach(() => vi.restoreAllMocks())

  it('shows the empty state and the manual panel form', async () => {
    const data: DataResponse = { timeRange: { from: 0, to: 1 }, panels: {} }
    mockApi({ [`${P}/dashboard`]: emptyDashboard, [`${P}/panels/data`]: data })

    render(<App />)

    expect(await screen.findByText('No panels yet')).toBeInTheDocument()
    expect(screen.getByText('Add a panel')).toBeInTheDocument()
    expect(screen.getByText('Default')).toBeInTheDocument()
  })

  it('shows the catalog banner while building', async () => {
    mockApi({
      [`${P}/dashboard`]: emptyDashboard,
      [`${P}/panels/data`]: { timeRange: { from: 0, to: 1 }, panels: {} },
      [`${P}/catalog/status`]: { ...catalogReady, state: 'building', metricCount: 0 },
    })

    render(<App />)

    expect(await screen.findByRole('status')).toHaveTextContent('Building the metric catalog')
  })

  it('warns when Prometheus is unreachable', async () => {
    mockApi({
      [`${P}/status`]: {
        project,
        prometheus: { ...prometheusOk, reachable: false, error: 'cannot reach Prometheus at http://prom:9090' },
      },
      [`${P}/dashboard`]: emptyDashboard,
      [`${P}/panels/data`]: { timeRange: { from: 0, to: 1 }, panels: {} },
    })

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Prometheus is unreachable')
  })

  it('offers a retry when the backend is down', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('connection refused'))

    render(<App />)

    expect(await screen.findByText("Can't reach the PromPilot backend")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})

describe('App without projects', () => {
  beforeEach(() => useDashboard.setState(initialState))
  afterEach(() => vi.restoreAllMocks())

  it('invites the user to create the first project', async () => {
    mockApi({ '/api/projects': [] })
    render(<App />)
    expect(await screen.findByText('Connect your first Prometheus')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New project' })).toBeInTheDocument()
  })
})
