import { create } from 'zustand'
import type { ChatTurnRecord, PanelPlacement } from '../api/types'
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
  /**
   * One conversation per project/dashboard, keyed `slug/dashboardId`. The server
   * holds the transcript; this is the loaded copy plus the turn being streamed.
   */
  conversations: Record<string, ChatTurn[]>
  /** Highest server sequence number seen per conversation, for incremental polls. */
  lastSeq: Record<string, number>
  sending: boolean
  send: (message: string, playbook?: { name: string; title: string }) => Promise<void>
  stop: () => void
  clear: () => Promise<void>
  /** Load the active conversation from the server (full when `reset`, otherwise only newer turns). */
  sync: (reset?: boolean) => Promise<boolean>
}

/** The active project's turns. */
function conversationKey(): string | null {
  const { project, dashboardId } = useDashboard.getState()
  return project ? `${project}/${dashboardId ?? 'overview'}` : null
}

export const selectTurns = (state: ChatState): ChatTurn[] => state.conversations[conversationKey() ?? ''] ?? EMPTY_TURNS

const EMPTY_TURNS: ChatTurn[] = []

let controller: AbortController | null = null
const nextId = () => `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

/** Server records are already in the UI's shape; only the client-side flag is missing. */
const fromRecord = (r: ChatTurnRecord): ChatTurn => ({
  id: r.id,
  role: r.role,
  content: r.content,
  reasoning: r.reasoning,
  blocks: r.blocks as Block[],
  error: r.error,
  pending: false,
})

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

export const useChat = create<ChatState>()((set, get) => ({
  conversations: {},
  lastSeq: {},
  sending: false,

  async sync(reset = false) {
    const key = conversationKey()
    if (!key) return false
    const after = reset ? 0 : (get().lastSeq[key] ?? 0)
    const history = await currentApi().chatHistory(after)
    if (conversationKey() !== key) return false
    const fresh = history.turns.map(fromRecord)
    set((s) => {
      const current = s.conversations[key] ?? EMPTY_TURNS
      const known = new Set(current.map((t) => t.id))
      const merged = reset ? fresh : [...current, ...fresh.filter((t) => !known.has(t.id))]
      return {
        conversations: { ...s.conversations, [key]: merged },
        lastSeq: { ...s.lastSeq, [key]: Math.max(history.lastSeq, s.lastSeq[key] ?? 0) },
      }
    })
    return fresh.length > 0
  },

  async send(message, playbook) {
    const text = message.trim()
    const project = conversationKey()
    if ((!text && !playbook) || get().sending || !project) return
    const shown = playbook ? `Run playbook: ${playbook.title}${text ? ` — ${text}` : ''}` : text
    const chatUrl = currentApi().chatUrl

    const turnsOf = (s: ChatState) => s.conversations[project] ?? EMPTY_TURNS
    const setTurns = (fn: (turns: ChatTurn[]) => ChatTurn[]) =>
      set((s) => ({ conversations: { ...s.conversations, [project]: fn(turnsOf(s)) } }))

    const assistant: ChatTurn = { id: nextId(), role: 'assistant', content: '', reasoning: '', blocks: [], error: null, pending: true }
    const user: ChatTurn = { id: nextId(), role: 'user', content: shown, reasoning: '', blocks: [], error: null, pending: false }
    set({ sending: true })
    setTurns((turns) => [...turns, user, assistant])

    const update = (fn: (turn: ChatTurn) => ChatTurn) => setTurns((turns) => turns.map((t) => (t.id === assistant.id ? fn(t) : t)))
    // The server names both turns; adopt its ids so a later sync recognises them.
    const adopt = (userId: string, assistantId: string) => {
      setTurns((turns) => turns.map((t) => (t.id === user.id ? { ...t, id: userId } : t.id === assistant.id ? { ...t, id: assistantId } : t)))
      user.id = userId
      assistant.id = assistantId
    }
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
        { message: text, playbook: playbook?.name, lang: navigator.language },
        ({ event, data }) => {
          const d = data as Record<string, unknown>
          switch (event) {
            case 'turn':
              adopt(String(d.userId), String(d.assistantId))
              break
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
      // Pick up the server's copy (sequence numbers, anything others added meanwhile).
      void get().sync().catch(() => undefined)
    }
  },

  stop() {
    controller?.abort()
  },

  async clear() {
    get().stop()
    const key = conversationKey()
    if (!key) return
    await currentApi().clearChatHistory()
    set((s) => ({ conversations: { ...s.conversations, [key]: [] }, lastSeq: { ...s.lastSeq, [key]: 0 } }))
  },
}))

// Transcripts used to live in localStorage; the server holds them now.
try {
  localStorage.removeItem('prompilot.chat')
} catch {
  /* storage may be unavailable */
}
