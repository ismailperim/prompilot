import { streamSse, type SseEvent } from './sse'

function responseFrom(chunks: string[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c))
      controller.close()
    },
  })
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

describe('streamSse', () => {
  afterEach(() => vi.restoreAllMocks())

  it('parses events split across chunks', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      responseFrom(['event: text_delta\ndata: {"text":"Hel', 'lo"}\n\nevent: done\nda', 'ta: {"stopped":"answered"}\n\n']),
    )
    const events: SseEvent[] = []
    await streamSse('/api/chat', { message: 'x' }, (e) => events.push(e))
    expect(events).toEqual([
      { event: 'text_delta', data: { text: 'Hello' } },
      { event: 'done', data: { stopped: 'answered' } },
    ])
  })

  it('surfaces the server detail on error responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'No LLM configured.' }), { status: 503 }),
    )
    await expect(streamSse('/api/chat', {}, () => {})).rejects.toThrow('No LLM configured.')
  })
})
