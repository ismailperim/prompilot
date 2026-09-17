import { Copy, GripVertical, Pencil, Table2, X } from 'lucide-react'
import { createElement, useState } from 'react'
import type { PanelData, PanelSpec } from '../api/types'
import { PanelErrorBoundary } from './ErrorBoundary'
import { InspectDialog } from './InspectDialog'
import { rendererFor } from './registry'

interface Props {
  spec: PanelSpec
  data: PanelData | undefined
  timeRange: { from: number; to: number } | null
  refreshing: boolean
  onRemove: () => void
  onEdit: () => void
  onDuplicate: () => void
}

export function PanelFrame({ spec, data, timeRange, refreshing, onRemove, onEdit, onDuplicate }: Props) {
  const renderer = rendererFor(spec.type)
  const [confirming, setConfirming] = useState(false)
  const [inspecting, setInspecting] = useState(false)
  const expr = spec.queries.map((q) => q.expr).join('   ·   ')

  return (
    <section className="panel" aria-label={spec.title}>
      <header className="panel__header drag-handle">
        <span className="panel__grip" aria-hidden="true">
          <GripVertical size={14} />
        </span>
        <div className="panel__heading">
          <h2 className="panel__title" title={spec.description || spec.title}>
            {spec.title}
          </h2>
          <code className="panel__expr" title={expr}>
            {expr}
          </code>
        </div>
        <div className="panel__actions" onPointerDown={(e) => e.stopPropagation()}>
          {refreshing && <span className="pulse" aria-label="Refreshing" />}
          {confirming ? (
            <>
              <button className="btn btn--danger btn--xs" onClick={onRemove}>
                Remove
              </button>
              <button className="btn btn--ghost btn--xs" onClick={() => setConfirming(false)}>
                Keep
              </button>
            </>
          ) : (
            <>
              <button className="btn btn--icon btn--ghost btn--xs" onClick={() => setInspecting(true)} aria-label={`Inspect ${spec.title}`} title="Inspect data" disabled={!data || !!data.error}>
                <Table2 size={14} />
              </button>
              <button className="btn btn--icon btn--ghost btn--xs" onClick={onEdit} aria-label={`Edit ${spec.title}`} title="Edit">
                <Pencil size={14} />
              </button>
              <button className="btn btn--icon btn--ghost btn--xs" onClick={onDuplicate} aria-label={`Duplicate ${spec.title}`} title="Duplicate">
                <Copy size={14} />
              </button>
              <button
                className="btn btn--icon btn--ghost btn--xs"
                onClick={() => setConfirming(true)}
                aria-label={`Remove ${spec.title}`}
                title="Remove"
              >
                <X size={14} />
              </button>
            </>
          )}
        </div>
      </header>
      <div className="panel__body">
        {data?.error ? (
          <div className="panel-message panel-message--error">
            <strong>Query failed</strong>
            <span>{data.error}</span>
          </div>
        ) : data ? (
          <PanelErrorBoundary key={JSON.stringify(spec)}>
            {createElement(renderer, { spec, frames: data.frames, timeRange })}
          </PanelErrorBoundary>
        ) : (
          <div className="panel-message">
            <span className="skeleton" aria-label="Loading" />
          </div>
        )}
        {data?.warnings?.length ? (
          <p className="panel__warning" title={data.warnings.join('\n')}>
            {data.warnings[0]}
          </p>
        ) : null}
      </div>
      {inspecting && data && <InspectDialog spec={spec} frames={data.frames} onClose={() => setInspecting(false)} />}
    </section>
  )
}
