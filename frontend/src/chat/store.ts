import { create } from 'zustand'
import type { PanelPlacement } from '../api/types'
import { useDashboard } from '../store/dashboard'
import { streamSse } from './sse'

export interface ToolStep {
  id: string
  name: string
  arguments: unknown
  ok?: boolean
  summary?: string
  result?: unknown
  startedAt: number
  finishedAt?: number
}

/** Assistant output in the order it happened: narration and tool steps interleaved. */
export type Block = { kind: 'text'; text: string } | { kind: 'step'; step: ToolStep }

export interface ChatTurn {
  id: string
  role: 'user' | 'assistant'
  /** Plain text of the turn (user message, or the assistant's narration joined). */
  content: string
  reasoning: string
  blocks: Block[]
  error: string | null
  pending: boolean
}

interface ChatState {
  turns: ChatTurn[]
  sending: boolean
  send: (message: string) => Promise<void>
  stop: () => void
  clear: () => void
}

let controller: AbortController | null = null
let counter = 0
const nextId = () => `t${++counter}`

/** Human-readable label for a tool call while it runs. */
export function describeStep(step: ToolStep): string {
  const a = (step.arguments ?? {}) as Record<string, unknown>
  switch (step.name) {
    case 'search_catalog':
      return `Searching metrics for “${String(a.query ?? '')}”`
    case 'query_prometheus':
      return `Testing query ${String(a.expr ?? '')}`
    case 'emit_panel':
      return `Adding panel “${String(a.title ?? '')}”`
    case 'patch_panel':
      return 'Updating panel'
    case 'remove_panel':
      return 'Removing panel'
    default:
      return step.name
  }
}

export const useChat = create<ChatState>((set, get) => ({
  turns: [],
  sending: false,

  async send(message) {
    const text = message.trim()
    if (!text || get().sending) return

    const history = get()
      .turns.filter((t) => t.content && !t.error)
      .map((t) => ({ role: t.role, content: t.content }))

    const assistant: ChatTurn = { id: nextId(), role: 'assistant', content: '', reasoning: '', blocks: [], error: null, pending: true }
    set((s) => ({
      sending: true,
      turns: [...s.turns, { id: nextId(), role: 'user', content: text, reasoning: '', blocks: [], error: null, pending: false }, assistant],
    }))

    const update = (fn: (turn: ChatTurn) => ChatTurn) =>
      set((s) => ({ turns: s.turns.map((t) => (t.id === assistant.id ? fn(t) : t)) }))
    const appendText = (delta: string) =>
      update((t) => {
        const last = t.blocks[t.blocks.length - 1]
        const blocks =
          last?.kind === 'text'
            ? [...t.blocks.slice(0, -1), { kind: 'text' as const, text: last.text + delta }]
            : [...t.blocks, { kind: 'text' as const, text: delta }]
        return { ...t, content: t.content + delta, blocks }
      })
    const addStep = (step: ToolStep) => update((t) => ({ ...t, blocks: [...t.blocks, { kind: 'step', step }] }))
    const updateStep = (id: string, fn: (step: ToolStep) => ToolStep) =>
      update((t) => ({
        ...t,
        blocks: t.blocks.map((b) => (b.kind === 'step' && b.step.id === id ? { kind: 'step', step: fn(b.step) } : b)),
      }))

    controller = new AbortController()
    const dashboard = useDashboard.getState()

    try {
      await streamSse(
        '/api/chat',
        { message: text, history },
        ({ event, data }) => {
          const d = data as Record<string, unknown>
          switch (event) {
            case 'text_delta':
              appendText(String(d.text ?? ''))
              break
            case 'reasoning_delta':
              update((t) => ({ ...t, reasoning: t.reasoning + String(d.text ?? '') }))
              break
            case 'tool_call':
              addStep({ id: String(d.id), name: String(d.name), arguments: d.arguments, startedAt: Date.now() })
              break
            case 'tool_result':
              updateStep(String(d.id), (st) => ({
                ...st,
                ok: Boolean(d.ok),
                summary: String(d.summary ?? ''),
                result: d.result,
                finishedAt: Date.now(),
              }))
              break
            case 'panel_added':
            case 'panel_updated':
              void dashboard.upsertPanel(d.panel as PanelPlacement)
              break
            case 'panel_removed':
              dashboard.dropPanel(String(d.id))
              break
            case 'error':
              update((t) => ({ ...t, error: String(d.message ?? 'Unknown error') }))
              break
            case 'done':
              break
          }
        },
        controller.signal,
      )
    } catch (error) {
      if (!controller.signal.aborted) {
        update((t) => ({ ...t, error: error instanceof Error ? error.message : String(error) }))
      } else {
        update((t) => ({ ...t, error: t.content ? null : 'Stopped.' }))
      }
    } finally {
      update((t) => ({ ...t, pending: false }))
      set({ sending: false })
      controller = null
    }
  },

  stop() {
    controller?.abort()
  },

  clear() {
    get().stop()
    set({ turns: [] })
  },
}))
