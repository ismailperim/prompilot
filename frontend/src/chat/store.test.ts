import { useDashboard } from '../store/dashboard'
import { selectTurns, useChat } from './store'

const sse = (events: string) => new Response(events, { status: 200, headers: { 'content-type': 'text/event-stream' } })
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })

describe('chat store', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    useChat.setState({ conversations: {}, lastSeq: {}, sending: false })
  })

  it('keeps one conversation per project and dashboard and adopts server ids', async () => {
    useDashboard.setState({ project: 'default', dashboardId: 'demo' })
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url.endsWith('/chat') && init?.method === 'POST') {
        return sse('event: turn\ndata: {"userId":"u1","assistantId":"a1"}\n\nevent: text_delta\ndata: {"text":"hi"}\n\nevent: done\ndata: {"stopped":"answered"}\n\n')
      }
      return json({ turns: [], lastSeq: 2 })
    })
    await useChat.getState().send('hello')
    const turns = selectTurns(useChat.getState())
    expect(turns.map((t) => [t.role, t.id])).toEqual([
      ['user', 'u1'],
      ['assistant', 'a1'],
    ])
    expect(turns[1].content).toBe('hi')
    expect(Object.keys(useChat.getState().conversations)).toEqual(['default/demo'])

    useDashboard.setState({ dashboardId: 'overview' })
    expect(selectTurns(useChat.getState())).toEqual([])
  })

  it('sync merges only unseen turns and tracks the sequence', async () => {
    useDashboard.setState({ project: 'default', dashboardId: 'demo' })
    const record = (id: string, seq: number, role: 'user' | 'assistant', content: string) => ({
      id,
      seq,
      role,
      content,
      reasoning: '',
      blocks: [{ kind: 'text', text: content }],
      error: null,
      createdAt: '2026-09-20T10:00:00Z',
    })
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    fetchMock.mockResolvedValueOnce(json({ turns: [record('u1', 1, 'user', 'cpu'), record('a1', 2, 'assistant', 'done')], lastSeq: 2 }))
    expect(await useChat.getState().sync(true)).toBe(true)
    expect(selectTurns(useChat.getState()).map((t) => t.id)).toEqual(['u1', 'a1'])
    expect(useChat.getState().lastSeq['default/demo']).toBe(2)

    fetchMock.mockResolvedValueOnce(json({ turns: [record('a1', 2, 'assistant', 'done'), record('u2', 3, 'user', 'mem')], lastSeq: 3 }))
    expect(await useChat.getState().sync()).toBe(true)
    expect(String(fetchMock.mock.calls[1][0])).toContain('after=2')
    expect(selectTurns(useChat.getState()).map((t) => t.id)).toEqual(['u1', 'a1', 'u2'])

    fetchMock.mockResolvedValueOnce(json({ turns: [], lastSeq: 3 }))
    expect(await useChat.getState().sync()).toBe(false)
  })
})
