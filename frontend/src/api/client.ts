import type {
  CatalogStatus,
  Dashboard,
  DataResponse,
  InstanceStatus,
  KnowledgeStatus,
  Layout,
  MetricEntry,
  NewPanelSpec,
  PanelPlacement,
  PanelSpec,
  PanelTypeInfo,
  Project,
  ProjectInput,
  ProjectStatus,
  SearchResponse,
  TimeRange,
} from './types'

export class ApiError extends Error {
  status: number
  /** Validation messages from a 422, when present. */
  details: string[]

  constructor(status: number, message: string, details: string[] = []) {
    super(message)
    this.status = status
    this.details = details
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  })
  if (response.status === 204) return undefined as T
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail
    if (Array.isArray(detail)) {
      const messages = detail.map((d) =>
        typeof d === 'string' ? d : `${(d as { loc?: unknown[] }).loc?.join('.')}: ${(d as { msg?: string }).msg}`,
      )
      throw new ApiError(response.status, messages.join('; '), messages)
    }
    throw new ApiError(response.status, typeof detail === 'string' ? detail : `Request failed (${response.status})`)
  }
  return body as T
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) })

/** Everything scoped to one project lives under /api/projects/{slug}. */
export function projectApi(slug: string) {
  const base = `/api/projects/${encodeURIComponent(slug)}`
  return {
    base,
    status: () => request<ProjectStatus>(`${base}/status`),
    dashboard: () => request<Dashboard>(`${base}/dashboard`),
    updateDashboard: (settings: { title?: string; timeRange?: TimeRange; refresh?: string; clearRefresh?: boolean }) =>
      request<Dashboard>(`${base}/dashboard`, { method: 'PATCH', ...json(settings) }),
    updateLayout: (updates: { id: string; layout: Layout }[]) =>
      request<Dashboard>(`${base}/dashboard/layout`, { method: 'PUT', ...json(updates) }),
    addPanel: (spec: NewPanelSpec, layout?: Layout) =>
      request<PanelPlacement>(`${base}/panels`, { method: 'POST', ...json({ spec, layout }) }),
    patchPanel: (id: string, changes: Partial<NewPanelSpec>) =>
      request<PanelPlacement>(`${base}/panels/${id}`, { method: 'PATCH', ...json(changes) }),
    deletePanel: (id: string) => request<void>(`${base}/panels/${id}`, { method: 'DELETE' }),
    panelsData: (body: { ids?: string[]; timeRange?: TimeRange }, signal?: AbortSignal) =>
      request<DataResponse>(`${base}/panels/data`, { method: 'POST', ...json(body), signal }),
    exportUrl: `${base}/export/grafana`,
    chatUrl: `${base}/chat`,
    catalogStatus: () => request<CatalogStatus>(`${base}/catalog/status`),
    catalogSearch: (q: string, opts: { limit?: number; category?: string } = {}, signal?: AbortSignal) => {
      const params = new URLSearchParams({ q, limit: String(opts.limit ?? 30) })
      if (opts.category) params.set('category', opts.category)
      return request<SearchResponse>(`${base}/catalog/search?${params}`, { signal })
    },
    catalogMetric: (name: string) => request<MetricEntry>(`${base}/catalog/metrics/${encodeURIComponent(name)}`),
    catalogRebuild: () => request<{ started: boolean; status: CatalogStatus }>(`${base}/catalog/rebuild`, { method: 'POST' }),
    knowledge: () => request<KnowledgeStatus>(`${base}/knowledge`),
    knowledgeDoc: (name: string) => request<{ name: string; body: string; source: string }>(`${base}/knowledge/docs/${encodeURIComponent(name)}`),
    createKnowledgeDoc: (title: string, body: string) =>
      request<{ name: string; body: string; source: string }>(`${base}/knowledge/docs`, { method: 'POST', ...json({ title, body }) }),
    putKnowledgeDoc: (name: string, body: string) =>
      request<{ name: string; body: string; source: string }>(`${base}/knowledge/docs/${encodeURIComponent(name)}`, { method: 'PUT', ...json({ body }) }),
    deleteKnowledgeDoc: (name: string) => request<void>(`${base}/knowledge/docs/${encodeURIComponent(name)}`, { method: 'DELETE' }),
    putKnowledgePrompt: (prompt: string) => request<KnowledgeStatus>(`${base}/knowledge/prompt`, { method: 'PUT', ...json({ prompt }) }),
  }
}

export type ProjectApi = ReturnType<typeof projectApi>

export const api = {
  status: () => request<InstanceStatus>('/api/status'),
  panelTypes: () => request<PanelTypeInfo[]>('/api/panels/types'),
  validatePanel: (spec: NewPanelSpec) => request<PanelSpec>('/api/panels/validate', { method: 'POST', ...json(spec) }),
  projects: {
    list: () => request<Project[]>('/api/projects'),
    create: (input: ProjectInput) => request<Project>('/api/projects', { method: 'POST', ...json(input) }),
    update: (slug: string, input: Partial<ProjectInput> & { clearPassword?: boolean }) =>
      request<Project>(`/api/projects/${encodeURIComponent(slug)}`, { method: 'PATCH', ...json(input) }),
    remove: (slug: string) => request<void>(`/api/projects/${encodeURIComponent(slug)}`, { method: 'DELETE' }),
    test: (input: { prometheusUrl: string; prometheusUsername?: string | null; prometheusPassword?: string | null }) =>
      request<{ ok: boolean; version: string | null; error: string | null }>('/api/projects/test', { method: 'POST', ...json(input) }),
  },
  project: projectApi,
}
