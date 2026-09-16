import type { ComponentType } from 'react'
import type { DataFrame, PanelSpec } from '../api/types'

export interface PanelRendererProps {
  spec: PanelSpec
  frames: DataFrame[]
  /** Absolute range the frames were fetched for, epoch ms. */
  timeRange: { from: number; to: number } | null
}

export type PanelRenderer = ComponentType<PanelRendererProps>
