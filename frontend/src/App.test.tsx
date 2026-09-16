import { render, screen } from '@testing-library/react'
import App from './App'

describe('App', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows backend health when reachable', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ status: 'ok', prometheus_url: 'http://prom:9090', llm_enabled: false }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    render(<App />)

    expect(await screen.findByText('ok')).toBeInTheDocument()
    expect(screen.getByText('http://prom:9090')).toBeInTheDocument()
    expect(screen.getByText('not configured')).toBeInTheDocument()
  })

  it('shows an error when the backend is unreachable', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('connection refused'))

    render(<App />)

    expect(await screen.findByText(/Backend unreachable/)).toBeInTheDocument()
  })
})
