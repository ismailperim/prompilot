import type { CatalogStatus } from '../api/types'

export function CatalogBanner({ status, onRebuild }: { status: CatalogStatus | null; onRebuild: () => void }) {
  if (!status) return null
  if (status.state === 'building') {
    return (
      <div className="banner banner--info" role="status">
        <span className="panel__pulse" /> Building the metric catalog — discovering and indexing metrics from Prometheus…
      </div>
    )
  }
  if (status.state === 'error') {
    return (
      <div className="banner banner--error" role="alert">
        <strong>Metric catalog build failed.</strong> {status.error}{' '}
        <button className="link" onClick={onRebuild}>
          Try again
        </button>
      </div>
    )
  }
  return null
}
