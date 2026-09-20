import { create } from 'zustand'
import { api, ApiError, projectApi, type ProjectApi } from '../api/client'
import type {
  CatalogStatus,
  Dashboard,
  DashboardSummary,
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
  /** Dashboards of the active project; the active one is `dashboardId`. */
  dashboards: DashboardSummary[]
  dashboardId: string | null
  llm: SystemStatus['llm'] | null
  authEnabled: boolean
  dashboard: Dashboard | null
  status: SystemStatus | null
  catalog: CatalogStatus | null
  data: Record<string, PanelData>
  resolvedRange: { from: number; to: number } | null
  loading: boolean
  refreshing: boolean
  error: string | null

  load: () => Promise<void>
  selectProject: (slug: string, dashboardId?: string | null) => Promise<void>
  selectDashboard: (id: string) => Promise<void>
  reloadDashboards: () => Promise<void>
  /** Re-fetch the current dashboard in place (panels others added) and refresh its data. */
  reloadDashboard: () => Promise<void>
  createDashboard: (title: string, copyFrom?: string) => Promise<void>
  renameDashboard: (title: string) => Promise<void>
  deleteDashboard: (id: string) => Promise<void>
  duplicatePanel: (id: string) => Promise<void>
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
  | 'dashboards'
  | 'dashboardId'
  | 'llm'
  | 'authEnabled'
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
  dashboards: [],
  dashboardId: null,
  llm: null,
  authEnabled: false,
  dashboard: null,
  status: null,
  catalog: null,
  data: {},
  resolvedRange: null,
  loading: true,
  refreshing: false,
  error: null,
}

/** Project slug and dashboard id in the address bar (`/p/<slug>/d/<id>`), if any. */
export function fromLocation(): { slug: string | null; dashboardId: string | null } {
  const match = /^\/p\/([^/]+)(?:\/d\/([^/]+))?/.exec(window.location.pathname)
  return {
    slug: match ? decodeURIComponent(match[1]) : null,
    dashboardId: match?.[2] ? decodeURIComponent(match[2]) : null,
  }
}

function writeLocation(slug: string, dashboardId: string) {
  const path = `/p/${encodeURIComponent(slug)}/d/${encodeURIComponent(dashboardId)}`
  if (window.location.pathname !== path) window.history.pushState({}, '', path)
}

/** Bound API for the active project and dashboard; throws when none is selected. */
export function currentApi(): ProjectApi {
  const { project, dashboardId } = useDashboard.getState()
  if (!project) throw new Error('No project selected')
  return projectApi(project, dashboardId ?? 'overview')
}

export const useDashboard = create<DashboardState>((set, get) => ({
  ...initialState,

  async load() {
    set({ loading: true, error: null })
    try {
      const [instance, projects] = await Promise.all([api.status(), api.projects.list()])
      set({ llm: instance.llm, authEnabled: instance.auth_enabled, projects })
      const wanted = fromLocation()
      const first = projects.find((p) => p.slug === wanted.slug) ?? projects[0]
      if (!first) {
        set({ loading: false, dashboard: null, project: null })
        return
      }
      await get().selectProject(first.slug, wanted.slug === first.slug ? wanted.dashboardId : null)
    } catch (error) {
      set({ loading: false, error: describe(error) })
    }
  },

  async selectProject(slug, dashboardId = null) {
    inflight?.abort()
    set({ project: slug, dashboardId: null, dashboards: [], dashboard: null, data: {}, resolvedRange: null, catalog: null, status: null, loading: true, error: null })
    try {
      const dashboards = await projectApi(slug).dashboards()
      if (get().project !== slug) return
      const chosen = dashboards.find((d) => d.id === dashboardId) ?? dashboards[0]
      set({ dashboards })
      await Promise.all([get().selectDashboard(chosen?.id ?? 'overview'), get().checkStatus(), get().loadCatalogStatus()])
    } catch (error) {
      set({ loading: false, error: describe(error) })
    }
  },

  async selectDashboard(id) {
    const slug = get().project
    if (!slug) return
    inflight?.abort()
    writeLocation(slug, id)
    set({ dashboardId: id, dashboard: null, data: {}, resolvedRange: null, loading: true, error: null })
    try {
      const dashboard = await projectApi(slug, id).dashboard()
      if (get().project !== slug || get().dashboardId !== id) return
      set({ dashboard, loading: false })
      await get().refresh()
    } catch (error) {
      set({ loading: false, error: describe(error) })
    }
  },

  async reloadDashboard() {
    const { project, dashboardId } = get()
    if (!project || !dashboardId) return
    const dashboard = await projectApi(project, dashboardId).dashboard()
    if (get().project !== project || get().dashboardId !== dashboardId) return
    set({ dashboard })
    await get().refresh()
  },

  async reloadDashboards() {
    const slug = get().project
    if (!slug) return
    set({ dashboards: await projectApi(slug).dashboards() })
  },

  async createDashboard(title, copyFrom) {
    const created = await currentApi().createDashboard(title, copyFrom)
    await get().reloadDashboards()
    await get().selectDashboard(created.id)
  },

  async renameDashboard(title) {
    const dashboard = await currentApi().updateDashboard({ title })
    set({ dashboard })
    await get().reloadDashboards()
  },

  async deleteDashboard(id) {
    await currentApi().deleteDashboard(id)
    await get().reloadDashboards()
    if (get().dashboardId === id) {
      const next = get().dashboards[0]
      if (next) await get().selectDashboard(next.id)
    }
  },

  async duplicatePanel(id) {
    const placement = await currentApi().duplicatePanel(id)
    await get().upsertPanel(placement)
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
    const { dashboard, project, dashboardId } = get()
    if (!dashboard || !project || !dashboardId) return
    if (!ids) inflight?.abort()
    const controller = new AbortController()
    if (!ids) inflight = controller
    set({ refreshing: true })
    try {
      const response = await projectApi(project, dashboardId).panelsData({ ids, timeRange: dashboard.timeRange }, controller.signal)
      if (get().project !== project || get().dashboardId !== dashboardId) return
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
