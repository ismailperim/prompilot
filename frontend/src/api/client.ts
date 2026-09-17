import type {
  CatalogStatus,
  Dashboard,
  DataResponse,
  KnowledgeStatus,
  MetricEntry,
  Layout,
  NewPanelSpec,
  PanelPlacement,
  PanelSpec,
  PanelTypeInfo,
  SearchResponse,
  SystemStatus,
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

export const api = {
  status: () => request<SystemStatus>('/api/status'),
  dashboard: () => request<Dashboard>('/api/dashboard'),
  updateDashboard: (settings: { title?: string; timeRange?: TimeRange; refresh?: string; clearRefresh?: boolean }) =>
    request<Dashboard>('/api/dashboard', { method: 'PATCH', ...json(settings) }),
  updateLayout: (updates: { id: string; layout: Layout }[]) =>
    request<Dashboard>('/api/dashboard/layout', { method: 'PUT', ...json(updates) }),
  panelTypes: () => request<PanelTypeInfo[]>('/api/panels/types'),
  addPanel: (spec: NewPanelSpec, layout?: Layout) =>
    request<PanelPlacement>('/api/panels', { method: 'POST', ...json({ spec, layout }) }),
  patchPanel: (id: string, changes: Partial<NewPanelSpec>) =>
    request<PanelPlacement>(`/api/panels/${id}`, { method: 'PATCH', ...json(changes) }),
  deletePanel: (id: string) => request<void>(`/api/panels/${id}`, { method: 'DELETE' }),
  validatePanel: (spec: NewPanelSpec) => request<PanelSpec>('/api/panels/validate', { method: 'POST', ...json(spec) }),
  panelsData: (body: { ids?: string[]; timeRange?: TimeRange }, signal?: AbortSignal) =>
    request<DataResponse>('/api/panels/data', { method: 'POST', ...json(body), signal }),
  catalogStatus: () => request<CatalogStatus>('/api/catalog/status'),
  knowledge: () => request<KnowledgeStatus>('/api/knowledge'),
  catalogSearch: (q: string, opts: { limit?: number; category?: string } = {}, signal?: AbortSignal) => {
    const params = new URLSearchParams({ q, limit: String(opts.limit ?? 30) })
    if (opts.category) params.set('category', opts.category)
    return request<SearchResponse>(`/api/catalog/search?${params}`, { signal })
  },
  catalogMetric: (name: string) => request<MetricEntry>(`/api/catalog/metrics/${encodeURIComponent(name)}`),
  catalogRebuild: () => request<{ started: boolean; status: CatalogStatus }>('/api/catalog/rebuild', { method: 'POST' }),
}
