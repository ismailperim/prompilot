export interface SseEvent {
  event: string
  data: unknown
}

/**
 * POST a JSON body and read the Server-Sent Events response. EventSource only
 * supports GET, so this parses the stream by hand.
 */
export async function streamSse(
  url: string,
  body: unknown,
  onEvent: (event: SseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) {
    const detail = await response.json().then((b: { detail?: unknown }) => b.detail).catch(() => null)
    throw new Error(typeof detail === 'string' ? detail : `Chat request failed (${response.status})`)
  }
  if (!response.body) throw new Error('No response body')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const flush = (block: string) => {
    let event = 'message'
    const dataLines: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    }
    if (dataLines.length === 0) return
    const raw = dataLines.join('\n')
    let data: unknown = raw
    try {
      data = JSON.parse(raw)
    } catch {
      /* keep raw text */
    }
    onEvent({ event, data })
  }

  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let index: number
    while ((index = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, index)
      buffer = buffer.slice(index + 2)
      if (block.trim()) flush(block)
    }
  }
  if (buffer.trim()) flush(buffer)
}
