import { render, screen } from '@testing-library/react'
import App from './App'
import type { Dashboard, DataResponse, SystemStatus } from './api/types'
import { initialState, useDashboard } from './store/dashboard'

const status: SystemStatus = {
  prometheus: { url: 'http://prom:9090', reachable: true, version: '3.5.0', error: null },
  llm: { enabled: false, model: null },
}

const emptyDashboard: Dashboard = {
  version: 1,
  title: 'Overview',
  timeRange: { from: 'now-1h', to: 'now' },
  refresh: '30s',
  panels: [],
}

function mockApi(routes: Record<string, unknown>) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = typeof input === 'string' ? input : (input as Request).url
    const path = url.replace(/^https?:\/\/[^/]+/, '')
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
    mockApi({ '/api/status': status, '/api/dashboard': emptyDashboard, '/api/panels/data': data })

    render(<App />)

    expect(await screen.findByText('No panels yet')).toBeInTheDocument()
    expect(screen.getByText('Add a panel')).toBeInTheDocument()
    expect(screen.getByText('Overview')).toBeInTheDocument()
  })

  it('warns when Prometheus is unreachable', async () => {
    const down: SystemStatus = {
      ...status,
      prometheus: { ...status.prometheus, reachable: false, error: 'cannot reach Prometheus at http://prom:9090' },
    }
    mockApi({ '/api/status': down, '/api/dashboard': emptyDashboard, '/api/panels/data': { timeRange: { from: 0, to: 1 }, panels: {} } })

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
