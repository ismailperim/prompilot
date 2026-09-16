import type { SystemStatus } from '../api/types'

export function StatusBanner({ status, error }: { status: SystemStatus | null; error: string | null }) {
  if (error) {
    return (
      <div className="banner banner--error" role="alert">
        <strong>Something went wrong.</strong> {error}
      </div>
    )
  }
  if (status && !status.prometheus.reachable) {
    return (
      <div className="banner banner--error" role="alert">
        <strong>Prometheus is unreachable</strong> at <code>{status.prometheus.url}</code>.{' '}
        {status.prometheus.error} Panels will show errors until it is back.
      </div>
    )
  }
  return null
}
