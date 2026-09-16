import type { PanelRendererProps } from './types'

/** Fallback when the backend knows a panel type the UI doesn't (yet). Never crashes. */
export function Unknown({ spec }: PanelRendererProps) {
  return (
    <div className="panel-fallback">
      <p className="panel-fallback__title">
        No renderer for panel type <code>{spec.type}</code>
      </p>
      <p className="panel-fallback__hint">
        The panel is saved and will export to Grafana. Update PromPilot to see it here.
      </p>
      <pre className="panel-fallback__json">{JSON.stringify(spec, null, 2)}</pre>
    </div>
  )
}
