import { create } from 'zustand'
import { api, ApiError, projectApi, type ProjectApi } from '../api/client'
import type {
  CatalogStatus,
  Dashboard,
  Layout,
  NewPanelSpec,
  PanelData,
  PanelPlacement,
  Project,
  SystemStatus,
  TimeRange,
} from '../api/types'

interface DashboardState {
  /** All projects on this instance; the active one is `project`. */
  projects: Project[]
  project: string | null
  llm: SystemStatus['llm'] | null
  dashboard: Dashboard | null
  status: SystemStatus | null
  catalog: CatalogStatus | null
  data: Record<string, PanelData>
  resolvedRange: { from: number; to: number } | null
  loading: boolean
  refreshing: boolean
  error: string | null

  load: () => Promise<void>
  selectProject: (slug: string) => Promise<void>
  reloadProjects: () => Promise<void>
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
  /** Apply a panel the server already saved (e.g. created by the chat agent) and fetch its data. */
  upsertPanel: (placement: PanelPlacement) => Promise<void>
  /** Drop a panel the server already removed. */
  dropPanel: (id: string) => void
}

const describe = (error: unknown): string =>
  error instanceof ApiError || error instanceof Error ? error.message : String(error)

let inflight: AbortController | null = null

type Data = Pick<
  DashboardState,
  | 'projects'
  | 'project'
  | 'llm'
  | 'dashboard'
  | 'status'
  | 'catalog'
  | 'data'
  | 'resolvedRange'
  | 'loading'
  | 'refreshing'
  | 'error'
>

export const initialState: Data = {
  projects: [],
  project: null,
  llm: null,
  dashboard: null,
  status: null,
  catalog: null,
  data: {},
  resolvedRange: null,
  loading: true,
  refreshing: false,
  error: null,
}

/** The slug in the address bar (`/p/<slug>`), if any. */
export function slugFromLocation(): string | null {
  const match = /^\/p\/([^/]+)/.exec(window.location.pathname)
  return match ? decodeURIComponent(match[1]) : null
}

function writeLocation(slug: string) {
  const path = `/p/${encodeURIComponent(slug)}`
  if (window.location.pathname !== path) window.history.pushState({}, '', path)
}

/** Bound API for the active project; throws when none is selected. */
export function currentApi(): ProjectApi {
  const slug = useDashboard.getState().project
  if (!slug) throw new Error('No project selected')
  return projectApi(slug)
}

export const useDashboard = create<DashboardState>((set, get) => ({
  ...initialState,

  async load() {
    set({ loading: true, error: null })
    try {
      const [instance, projects] = await Promise.all([api.status(), api.projects.list()])
      set({ llm: instance.llm, projects })
      const wanted = slugFromLocation()
      const first = projects.find((p) => p.slug === wanted) ?? projects[0]
      if (!first) {
        set({ loading: false, dashboard: null, project: null })
        return
      }
      await get().selectProject(first.slug)
    } catch (error) {
      set({ loading: false, error: describe(error) })
    }
  },

  async selectProject(slug) {
    inflight?.abort()
    writeLocation(slug)
    set({ project: slug, dashboard: null, data: {}, resolvedRange: null, catalog: null, status: null, loading: true, error: null })
    try {
      const client = projectApi(slug)
      const [dashboard] = await Promise.all([client.dashboard(), get().checkStatus(), get().loadCatalogStatus()])
      if (get().project !== slug) return // switched again meanwhile
      set({ dashboard, loading: false })
      await get().refresh()
    } catch (error) {
      set({ loading: false, error: describe(error) })
    }
  },

  async reloadProjects() {
    const projects = await api.projects.list()
    set({ projects })
  },

  async checkStatus() {
    const slug = get().project
    if (!slug) return
    try {
      const status = await projectApi(slug).status()
      if (get().project !== slug) return
      set({ status: { prometheus: status.prometheus, llm: get().llm ?? { enabled: false, model: null } } })
    } catch {
      set({ status: null })
    }
  },

  async loadCatalogStatus() {
    const slug = get().project
    if (!slug) return
    try {
      const catalog = await projectApi(slug).catalogStatus()
      if (get().project === slug) set({ catalog })
    } catch {
      set({ catalog: null })
    }
  },

  async rebuildCatalog() {
    const { status } = await currentApi().catalogRebuild()
    set({ catalog: status })
  },

  async refresh(ids) {
    const { dashboard, project } = get()
    if (!dashboard || !project) return
    if (!ids) inflight?.abort()
    const controller = new AbortController()
    if (!ids) inflight = controller
    set({ refreshing: true })
    try {
      const response = await projectApi(project).panelsData({ ids, timeRange: dashboard.timeRange }, controller.signal)
      if (get().project !== project) return
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
    const dashboard = await currentApi().updateDashboard({ timeRange })
    set({ dashboard })
    await get().refresh()
  },

  async setRefreshInterval(refresh) {
    const dashboard = await currentApi().updateDashboard(refresh ? { refresh } : { clearRefresh: true })
    set({ dashboard })
  },

  async addPanel(spec) {
    const placement = await currentApi().addPanel(spec)
    set((state) =>
      state.dashboard ? { dashboard: { ...state.dashboard, panels: [...state.dashboard.panels, placement] } } : {},
    )
    await get().refresh([placement.spec.id])
  },

  async patchPanel(id, changes) {
    const placement = await currentApi().patchPanel(id, changes)
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
    await currentApi().deletePanel(id)
    get().dropPanel(id)
  },

  async upsertPanel(placement) {
    set((state) => {
      if (!state.dashboard) return {}
      const exists = state.dashboard.panels.some((p) => p.spec.id === placement.spec.id)
      const panels = exists
        ? state.dashboard.panels.map((p) => (p.spec.id === placement.spec.id ? placement : p))
        : [...state.dashboard.panels, placement]
      return { dashboard: { ...state.dashboard, panels } }
    })
    await get().refresh([placement.spec.id])
  },

  dropPanel(id) {
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
    await currentApi().updateLayout(updates)
  },
}))
