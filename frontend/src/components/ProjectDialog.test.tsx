import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ProjectDialog } from './ProjectDialog'

type Call = { path: string; body: Record<string, unknown> }

function mockFetch(responses: Record<string, unknown>): Call[] {
  const calls: Call[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = typeof input === 'string' ? input : (input as Request).url
    const path = url.replace(/^https?:\/\/[^/]+/, '')
    calls.push({ path, body: init?.body ? JSON.parse(String(init.body)) : {} })
    const body = responses[path] ?? { detail: `no route for ${path}` }
    return new Response(JSON.stringify(body), { status: path in responses ? 200 : 404, headers: { 'Content-Type': 'application/json' } })
  })
  return calls
}

describe('ProjectDialog, Grafana source', () => {
  afterEach(() => vi.restoreAllMocks())

  it('lists Grafana datasources and tests through the proxy', async () => {
    const calls = mockFetch({
      '/api/projects/grafana/datasources': {
        ok: true,
        datasources: [
          { uid: 'mimir', name: 'Mimir', isDefault: true },
          { uid: 'prom', name: 'Prometheus', isDefault: false },
        ],
        error: null,
      },
      '/api/projects/test': { ok: true, version: '3.5.0', error: null },
    })
    render(<ProjectDialog project={null} onClose={() => {}} />)

    fireEvent.click(screen.getByRole('radio', { name: 'Through Grafana' }))
    fireEvent.change(screen.getByPlaceholderText('https://grafana.example.com'), { target: { value: 'https://grafana.example.com' } })
    fireEvent.change(screen.getByLabelText('Username (optional)'), { target: { value: 'viewer' } })
    fireEvent.change(screen.getByLabelText('Password (optional)'), { target: { value: 'pw' } })

    expect(screen.getByRole('button', { name: 'Test connection' })).toBeDisabled() // no datasource yet
    fireEvent.click(screen.getByRole('button', { name: 'Find datasources' }))

    const select = await screen.findByRole('combobox', { name: 'Prometheus datasource' })
    expect((select as HTMLSelectElement).value).toBe('mimir') // default datasource preselected
    expect(calls[0].body).toMatchObject({ grafanaUrl: 'https://grafana.example.com', prometheusUsername: 'viewer', prometheusPassword: 'pw' })

    fireEvent.change(select, { target: { value: 'prom' } })
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))
    await waitFor(() => expect(screen.getByText(/Connected/)).toHaveTextContent('Connected — Prometheus 3.5.0 via Grafana'))
    expect(calls[1].body).toMatchObject({ source: 'grafana', grafanaUrl: 'https://grafana.example.com', grafanaDatasourceUid: 'prom' })
    expect(calls[1].body).not.toHaveProperty('prometheusUrl')
  })

  it('shows why the datasource lookup failed', async () => {
    mockFetch({ '/api/projects/grafana/datasources': { ok: false, datasources: [], error: 'Grafana rejected the request (HTTP 401)' } })
    render(<ProjectDialog project={null} onClose={() => {}} />)
    fireEvent.click(screen.getByRole('radio', { name: 'Through Grafana' }))
    fireEvent.change(screen.getByPlaceholderText('https://grafana.example.com'), { target: { value: 'https://g.example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Find datasources' }))
    expect(await screen.findByText(/HTTP 401/)).toBeInTheDocument()
    // falls back to typing the UID by hand
    expect(screen.getByLabelText('Datasource UID')).toBeInTheDocument()
  })
})
