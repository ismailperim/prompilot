import { create } from 'zustand'
import { api, ApiError } from '../api/client'
import type { CatalogStatus, Dashboard, Layout, NewPanelSpec, PanelData, SystemStatus, TimeRange } from '../api/types'

interface DashboardState {
  dashboard: Dashboard | null
  status: SystemStatus | null
  catalog: CatalogStatus | null
  data: Record<string, PanelData>
  resolvedRange: { from: number; to: number } | null
  loading: boolean
  refreshing: boolean
  error: string | null

  load: () => Promise<void>
  checkStatus: () => Promise<void>
  loadCatalogStatus: () => Promise<void>
  rebuildCatalog: () => Promise<void>
  refresh: (ids?: string[]) => Promise<void>
  setTimeRange: (timeRange: TimeRange) => Promise<void>
  setRefreshInterval: (refresh: string | null) => Promise<void>
  addPanel: (spec: NewPanelSpec) => Promise<void>
  patchPanel: (id: string, changes: Partial<NewPanelSpec>) => Promise<void>
  removePanel: (id: string) => Promise<void>
  updateLayout: (updates: { id: string; layout: Layout }[]) => Promise<void>
}

const describe = (error: unknown): string =>
  error instanceof ApiError || error instanceof Error ? error.message : String(error)

let inflight: AbortController | null = null

type Data = Pick<
  DashboardState,
  'dashboard' | 'status' | 'catalog' | 'data' | 'resolvedRange' | 'loading' | 'refreshing' | 'error'
>

export const initialState: Data = {
  dashboard: null,
  status: null,
  catalog: null,
  data: {},
  resolvedRange: null,
  loading: true,
  refreshing: false,
  error: null,
}

export const useDashboard = create<DashboardState>((set, get) => ({
  ...initialState,

  async load() {
    set({ loading: true, error: null })
    try {
      const [dashboard] = await Promise.all([api.dashboard(), get().checkStatus(), get().loadCatalogStatus()])
      set({ dashboard, loading: false })
      await get().refresh()
    } catch (error) {
      set({ loading: false, error: describe(error) })
    }
  },

  async checkStatus() {
    try {
      set({ status: await api.status() })
    } catch {
      set({ status: null })
    }
  },

  async loadCatalogStatus() {
    try {
      set({ catalog: await api.catalogStatus() })
    } catch {
      set({ catalog: null })
    }
  },

  async rebuildCatalog() {
    const { status } = await api.catalogRebuild()
    set({ catalog: status })
  },

  async refresh(ids) {
    const { dashboard } = get()
    if (!dashboard) return
    if (!ids) inflight?.abort()
    const controller = new AbortController()
    if (!ids) inflight = controller
    set({ refreshing: true })
    try {
      const response = await api.panelsData({ ids, timeRange: dashboard.timeRange }, controller.signal)
      set((state) => ({
        data: ids ? { ...state.data, ...response.panels } : response.panels,
        resolvedRange: response.timeRange,
        refreshing: false,
      }))
    } catch (error) {
      if (controller.signal.aborted) return
      set({ refreshing: false, error: describe(error) })
    }
  },

  async setTimeRange(timeRange) {
    const dashboard = await api.updateDashboard({ timeRange })
    set({ dashboard })
    await get().refresh()
  },

  async setRefreshInterval(refresh) {
    const dashboard = await api.updateDashboard(refresh ? { refresh } : { clearRefresh: true })
    set({ dashboard })
  },

  async addPanel(spec) {
    const placement = await api.addPanel(spec)
    set((state) =>
      state.dashboard ? { dashboard: { ...state.dashboard, panels: [...state.dashboard.panels, placement] } } : {},
    )
    await get().refresh([placement.spec.id])
  },

  async patchPanel(id, changes) {
    const placement = await api.patchPanel(id, changes)
    set((state) =>
      state.dashboard
        ? {
            dashboard: {
              ...state.dashboard,
              panels: state.dashboard.panels.map((p) => (p.spec.id === id ? placement : p)),
            },
          }
        : {},
    )
    await get().refresh([id])
  },

  async removePanel(id) {
    await api.deletePanel(id)
    set((state) => {
      const data = { ...state.data }
      delete data[id]
      return state.dashboard
        ? { data, dashboard: { ...state.dashboard, panels: state.dashboard.panels.filter((p) => p.spec.id !== id) } }
        : { data }
    })
  },

  async updateLayout(updates) {
    // Optimistic: the grid already shows the new positions.
    set((state) => {
      if (!state.dashboard) return {}
      const byId = new Map(updates.map((u) => [u.id, u.layout]))
      return {
        dashboard: {
          ...state.dashboard,
          panels: state.dashboard.panels.map((p) => (byId.has(p.spec.id) ? { ...p, layout: byId.get(p.spec.id)! } : p)),
        },
      }
    })
    await api.updateLayout(updates)
  },
}))
