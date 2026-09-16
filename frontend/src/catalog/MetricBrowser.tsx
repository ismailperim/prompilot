import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { CatalogStatus, MetricEntry, SearchHit } from '../api/types'

interface Props {
  status: CatalogStatus | null
  onPick: (metric: MetricEntry) => void
  onRebuild: () => void
}

/** Search the metric catalog. Useful on its own, and the "I know roughly what I want" path into the form. */
export function MetricBrowser({ status, onPick, onRebuild }: Props) {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [hits, setHits] = useState<SearchHit[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const categories = Object.entries(status?.categories ?? {}).sort((a, b) => b[1] - a[1])

  useEffect(() => {
    if (!status || status.metricCount === 0) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setSearching(true)
      api
        .catalogSearch(query, { category: category || undefined }, controller.signal)
        .then((r) => {
          setHits(r.hits)
          setError(null)
        })
        .catch((e: unknown) => {
          if (!controller.signal.aborted) setError(e instanceof Error ? e.message : String(e))
        })
        .finally(() => {
          if (!controller.signal.aborted) setSearching(false)
        })
    }, 150)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [query, category, status])

  return (
    <div className="browser">
      <div className="browser__search">
        <input
          className="mono"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search metrics: cpu, memory available, http…"
          aria-label="Search metrics"
          spellCheck={false}
        />
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
          <option value="">All categories</option>
          {categories.map(([name, count]) => (
            <option key={name} value={name}>
              {name} ({count})
            </option>
          ))}
        </select>
      </div>

      <p className="browser__meta">
        {status?.state === 'building' && 'Building the catalog…'}
        {status?.state === 'error' && <span className="text-err">Catalog build failed: {status.error}</span>}
        {status?.state === 'ready' && `${status.metricCount} metrics · ${hits.length} shown`}
        {status?.state === 'idle' && 'Catalog not built yet.'}
        {searching && ' · searching'}
        {' · '}
        <button className="link" onClick={onRebuild} disabled={status?.state === 'building'}>
          Rebuild
        </button>
      </p>

      {error && <p className="form__error">{error}</p>}

      <ul className="metrics">
        {hits.map((m) => (
          <li key={m.name}>
            <button className="metric" onClick={() => onPick(m)} title="Use this metric in the panel form">
              <span className="metric__name">{m.name}</span>
              <span className="metric__tags">
                <span className={`tag tag--${m.type}`}>{m.type}</span>
                <span className="tag">{m.category}</span>
                {m.labels.length > 0 && <span className="metric__labels">{m.labels.join(' ')}</span>}
              </span>
              {m.help && <span className="metric__help">{m.help}</span>}
            </button>
          </li>
        ))}
        {status?.state === 'ready' && hits.length === 0 && !searching && (
          <li className="browser__empty">No metrics match. Try fewer words.</li>
        )}
      </ul>
    </div>
  )
}
