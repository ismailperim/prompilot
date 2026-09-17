// Wire types. These mirror the backend's Pydantic models (camelCase on the wire).

export type Unit =
  | 'none'
  | 'short'
  | 'percent'
  | 'percentunit'
  | 'bytes'
  | 'decbytes'
  | 'Bps'
  | 'bps'
  | 's'
  | 'ms'
  | 'ops'
  | 'reqps'
  | 'rps'
  | 'wps'

export const UNITS: { value: Unit; label: string }[] = [
  { value: 'short', label: 'Number' },
  { value: 'none', label: 'Raw' },
  { value: 'percent', label: 'Percent (0–100)' },
  { value: 'percentunit', label: 'Percent (0.0–1.0)' },
  { value: 'bytes', label: 'Bytes (IEC)' },
  { value: 'decbytes', label: 'Bytes (SI)' },
  { value: 'Bps', label: 'Bytes/s' },
  { value: 'bps', label: 'Bits/s' },
  { value: 's', label: 'Seconds' },
  { value: 'ms', label: 'Milliseconds' },
  { value: 'ops', label: 'Ops/s' },
  { value: 'reqps', label: 'Requests/s' },
  { value: 'rps', label: 'Reads/s' },
  { value: 'wps', label: 'Writes/s' },
]

export interface Query {
  refId: string
  expr: string
  legend: string | null
  instant: boolean
}

export interface PanelSpec {
  version: 1
  id: string
  type: string
  title: string
  description: string
  queries: Query[]
  unit: Unit
  timeFrom: string | null
  options: Record<string, unknown>
}

/** Spec as sent when creating a panel: the server fills in id/version/defaults. */
export type NewPanelSpec = Partial<Omit<PanelSpec, 'queries' | 'type' | 'title'>> & {
  type: string
  title: string
  queries: Partial<Query>[]
}

export interface Layout {
  x: number
  y: number
  w: number
  h: number
}

export interface PanelPlacement {
  spec: PanelSpec
  layout: Layout
}

export interface TimeRange {
  from: string
  to: string
}

export interface Dashboard {
  version: 1
  title: string
  timeRange: TimeRange
  refresh: string | null
  panels: PanelPlacement[]
}

export type FieldType = 'time' | 'number' | 'string'

export interface Field {
  name: string
  type: FieldType
  labels?: Record<string, string> | null
  values: (number | string | null)[]
}

export interface DataFrame {
  refId: string
  fields: Field[]
}

export interface PanelData {
  frames: DataFrame[]
  error: string | null
  warnings: string[]
}

export interface DataResponse {
  timeRange: { from: number; to: number }
  panels: Record<string, PanelData>
}

export interface PrometheusStatus {
  url: string
  reachable: boolean
  version: string | null
  error: string | null
}

export interface LLMStatus {
  enabled: boolean
  model: string | null
}

/** Instance-level status (`/api/status`). */
export interface InstanceStatus {
  llm: LLMStatus
  projects: number
  auth_enabled: boolean
  version: string
}

export interface Project {
  slug: string
  name: string
  prometheusUrl: string
  prometheusUsername: string | null
  hasPassword: boolean
  createdAt: string
  updatedAt: string
}

export interface ProjectInput {
  name: string
  slug?: string
  prometheusUrl: string
  prometheusUsername?: string | null
  prometheusPassword?: string | null
}

export interface ProjectStatus {
  project: Project
  prometheus: PrometheusStatus
}

/** What the UI works with: this project's Prometheus plus the instance's LLM. */
export interface SystemStatus {
  prometheus: PrometheusStatus
  llm: LLMStatus
}

export interface PanelTypeInfo {
  type: string
  description: string
  defaultLayout: [number, number]
  optionsSchema: Record<string, unknown>
}

export type CatalogState = 'idle' | 'building' | 'ready' | 'error'

export interface CatalogStatus {
  state: CatalogState
  metricCount: number
  updatedAt: string | null
  durationSeconds: number | null
  error: string | null
  categories: Record<string, number>
}

export interface MetricEntry {
  name: string
  type: string
  help: string
  unit: string
  category: string
  exporter: string | null
  labels: string[]
  labelsSampled: boolean
  note?: string | null
}

export interface SearchHit extends MetricEntry {
  score: number
}

export interface SearchResponse {
  query: string
  hits: SearchHit[]
}

export interface KnowledgeStatus {
  directory: string
  promptLoaded: boolean
  promptChars: number
  documents: { name: string; title: string; headings: string[]; chunks: number; size: number; updatedAt: string; source: string }[]
  chunks: number
  metricNotes: number
  playbooks: { name: string; title: string; description: string }[]
  prompt: string | null
  promptFromFiles: string | null
}
