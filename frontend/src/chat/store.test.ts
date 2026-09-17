import { useDashboard } from '../store/dashboard'
import { selectTurns, useChat } from './store'

describe('chat store keys', () => {
  it('keeps one conversation per project and dashboard', async () => {
    useDashboard.setState({ project: 'default', dashboardId: 'demo' })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('event: done\ndata: {"stopped":"answered"}\n\n', { status: 200 }),
    )
    await useChat.getState().send('hello')
    const turns = selectTurns(useChat.getState())
    expect(turns.map((t) => t.role)).toEqual(['user', 'assistant'])
    expect(Object.keys(useChat.getState().conversations)).toEqual(['default/demo'])

    useDashboard.setState({ dashboardId: 'overview' })
    expect(selectTurns(useChat.getState())).toEqual([])
    vi.restoreAllMocks()
  })
})
