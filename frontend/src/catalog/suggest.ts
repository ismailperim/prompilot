import type { MetricEntry, Unit } from '../api/types'

export interface Suggestion {
  expr: string
  legend: string
  unit: Unit
  title: string
}

/** A sensible first query for a metric, based on its type and naming conventions. */
export function suggestQuery(metric: MetricEntry): Suggestion {
  const { name, type, labels } = metric
  const legendLabel = pickLegendLabel(labels)
  const legend = legendLabel ? `{{${legendLabel}}}` : ''

  if (name.endsWith('_bucket') && (type === 'histogram' || type === 'unknown' || type === 'counter')) {
    const by = legendLabel ? `le, ${legendLabel}` : 'le'
    return {
      expr: `histogram_quantile(0.95, sum by (${by}) (rate(${name}[5m])))`,
      legend: legend || 'p95',
      unit: name.includes('seconds') ? 's' : name.includes('bytes') ? 'bytes' : 'short',
      title: `${humanize(name.replace(/_bucket$/, ''))} p95`,
    }
  }

  if (type === 'counter' || name.endsWith('_total')) {
    return {
      expr: `rate(${name}[5m])`,
      legend,
      unit: name.includes('_bytes') ? 'Bps' : name.includes('_seconds') ? 'percentunit' : 'ops',
      title: `${humanize(name.replace(/_total$/, ''))} rate`,
    }
  }

  return {
    expr: name,
    legend,
    unit: name.includes('_bytes') ? 'bytes' : name.includes('_seconds') ? 's' : name.includes('_ratio') ? 'percentunit' : 'short',
    title: humanize(name),
  }
}

const NOISE = new Set(['instance', 'job', '__name__'])

/** The most useful label to split series by: anything that isn't scrape plumbing. */
function pickLegendLabel(labels: string[]): string | null {
  const preferred = ['pod', 'container', 'namespace', 'device', 'mountpoint', 'cpu', 'mode', 'handler', 'method', 'code', 'status']
  for (const p of preferred) if (labels.includes(p)) return p
  const rest = labels.filter((l) => !NOISE.has(l))
  return rest[0] ?? (labels.includes('instance') ? 'instance' : null)
}

export function humanize(name: string): string {
  return name
    .replace(/^(node|kube|container|process|go|prometheus|http)_/, '')
    .replace(/_/g, ' ')
    .replace(/\b(bytes|seconds)\b/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^./, (c) => c.toUpperCase())
}
