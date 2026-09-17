import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { PanelPlacement } from '../api/types'
import { currentApi, useDashboard } from '../store/dashboard'
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
  /** One conversation per project slug. */
  conversations: Record<string, ChatTurn[]>
  sending: boolean
  send: (message: string, playbook?: { name: string; title: string }) => Promise<void>
  stop: () => void
  clear: () => void
}

/** The active project's turns. */
export const selectTurns = (state: ChatState): ChatTurn[] =>
  state.conversations[useDashboard.getState().project ?? ''] ?? EMPTY_TURNS

const EMPTY_TURNS: ChatTurn[] = []

let controller: AbortController | null = null
const nextId = () => `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

const MAX_TURNS = 60

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
    case 'save_note':
      return `Remembering “${String(a.title ?? '')}”`
    default:
      return step.name
  }
}

export const useChat = create<ChatState>()(
  persist(
    (set, get) => ({
  conversations: {},
  sending: false,

  async send(message, playbook) {
    const text = message.trim()
    const project = useDashboard.getState().project
    if ((!text && !playbook) || get().sending || !project) return
    const shown = playbook ? `Run playbook: ${playbook.title}${text ? ` — ${text}` : ''}` : text
    const chatUrl = currentApi().chatUrl

    const turnsOf = (s: ChatState) => s.conversations[project] ?? EMPTY_TURNS
    const setTurns = (fn: (turns: ChatTurn[]) => ChatTurn[]) =>
      set((s) => ({ conversations: { ...s.conversations, [project]: fn(turnsOf(s)) } }))

    const history = turnsOf(get())
      .filter((t) => t.content && !t.error)
      .map((t) => ({ role: t.role, content: t.content }))

    const assistant: ChatTurn = { id: nextId(), role: 'assistant', content: '', reasoning: '', blocks: [], error: null, pending: true }
    set({ sending: true })
    setTurns((turns) => [
      ...turns,
      { id: nextId(), role: 'user', content: shown, reasoning: '', blocks: [], error: null, pending: false },
      assistant,
    ])

    const update = (fn: (turn: ChatTurn) => ChatTurn) => setTurns((turns) => turns.map((t) => (t.id === assistant.id ? fn(t) : t)))
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
        chatUrl,
        { message: text, history, playbook: playbook?.name, lang: navigator.language },
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
    const project = useDashboard.getState().project
    if (!project) return
    set((s) => ({ conversations: { ...s.conversations, [project]: [] } }))
  },
    }),
    {
      name: 'prompilot.chat',
      version: 2,
      partialize: (state) => ({
        conversations: Object.fromEntries(
          Object.entries(state.conversations).map(([k, turns]) => [k, turns.slice(-MAX_TURNS)]),
        ),
      }),
      // A turn that was streaming when the page went away can never finish.
      onRehydrateStorage: () => (state) => {
        if (!state) return
        for (const [k, turns] of Object.entries(state.conversations)) {
          state.conversations[k] = turns.map((t) =>
            t.pending ? { ...t, pending: false, error: t.error ?? 'Interrupted by a page reload.' } : t,
          )
        }
      },
    },
  ),
)
