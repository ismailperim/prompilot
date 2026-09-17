import { useCallback, useMemo } from 'react'
import GridLayout, { useContainerWidth, verticalCompactor, type Layout, type LayoutItem } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import type { PanelPlacement } from '../api/types'
import { PanelFrame } from '../panels/PanelFrame'
import { useDashboard } from '../store/dashboard'

export const GRID_COLS = 24
export const ROW_HEIGHT = 30

interface Props {
  panels: PanelPlacement[]
  onEdit: (id: string) => void
}

export function DashboardGrid({ panels, onEdit }: Props) {
  const { width, containerRef, mounted } = useContainerWidth()
  const data = useDashboard((s) => s.data)
  const resolvedRange = useDashboard((s) => s.resolvedRange)
  const refreshing = useDashboard((s) => s.refreshing)
  const removePanel = useDashboard((s) => s.removePanel)
  const duplicatePanel = useDashboard((s) => s.duplicatePanel)
  const updateLayout = useDashboard((s) => s.updateLayout)

  const layout: Layout = useMemo(
    () => panels.map((p) => ({ i: p.spec.id, ...p.layout, minW: 3, minH: 3 })),
    [panels],
  )

  const persist = useCallback(
    (next: Layout) => {
      const current = new Map(panels.map((p) => [p.spec.id, p.layout]))
      const changed = next
        .filter((item: LayoutItem) => {
          const prev = current.get(item.i)
          return prev && (prev.x !== item.x || prev.y !== item.y || prev.w !== item.w || prev.h !== item.h)
        })
        .map((item: LayoutItem) => ({ id: item.i, layout: { x: item.x, y: item.y, w: item.w, h: item.h } }))
      if (changed.length) void updateLayout(changed)
    },
    [panels, updateLayout],
  )

  return (
    <div ref={containerRef} className="grid">
      {mounted && (
        <GridLayout
          width={width}
          layout={layout}
          gridConfig={{ cols: GRID_COLS, rowHeight: ROW_HEIGHT, margin: [12, 12], containerPadding: [0, 0] }}
          dragConfig={{ enabled: true, handle: '.drag-handle', bounded: false }}
          resizeConfig={{ enabled: true, handles: ['se', 'e', 's'] }}
          compactor={verticalCompactor}
          onDragStop={(l) => persist(l)}
          onResizeStop={(l) => persist(l)}
        >
          {panels.map((p) => (
            <div key={p.spec.id} className="grid__item">
              <PanelFrame
                spec={p.spec}
                data={data[p.spec.id]}
                timeRange={resolvedRange}
                refreshing={refreshing}
                onRemove={() => void removePanel(p.spec.id)}
                onEdit={() => onEdit(p.spec.id)}
                onDuplicate={() => void duplicatePanel(p.spec.id)}
              />
            </div>
          ))}
        </GridLayout>
      )}
    </div>
  )
}
