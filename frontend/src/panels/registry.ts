import { Stat } from './Stat'
import { Table } from './Table'
import { Timeseries } from './Timeseries'
import type { PanelRenderer } from './types'
import { Unknown } from './Unknown'

// type → renderer. Adding a panel type: one component + one line here.
const renderers: Record<string, PanelRenderer> = {
  timeseries: Timeseries,
  stat: Stat,
  table: Table,
}

export function rendererFor(type: string): PanelRenderer {
  return renderers[type] ?? Unknown
}

export function knownPanelTypes(): string[] {
  return Object.keys(renderers)
}
