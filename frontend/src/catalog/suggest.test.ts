import type { MetricEntry } from '../api/types'
import { humanize, suggestQuery } from './suggest'

const metric = (over: Partial<MetricEntry>): MetricEntry => ({
  name: 'x',
  type: 'gauge',
  help: '',
  unit: '',
  category: 'other',
  exporter: null,
  labels: [],
  labelsSampled: true,
  ...over,
})

describe('suggestQuery', () => {
  it('rates counters and picks a bytes/s unit for byte counters', () => {
    const s = suggestQuery(metric({ name: 'node_network_receive_bytes_total', type: 'counter', labels: ['device', 'instance', 'job'] }))
    expect(s.expr).toBe('rate(node_network_receive_bytes_total[5m])')
    expect(s.legend).toBe('{{device}}')
    expect(s.unit).toBe('Bps')
  })

  it('treats seconds counters as a fraction', () => {
    const s = suggestQuery(metric({ name: 'node_cpu_seconds_total', type: 'counter', labels: ['cpu', 'mode', 'instance'] }))
    expect(s.unit).toBe('percentunit')
    expect(s.legend).toBe('{{cpu}}')
  })

  it('builds a p95 for histogram buckets', () => {
    const s = suggestQuery(metric({ name: 'http_request_duration_seconds_bucket', type: 'histogram', labels: ['le', 'handler'] }))
    expect(s.expr).toBe('histogram_quantile(0.95, sum by (le, handler) (rate(http_request_duration_seconds_bucket[5m])))')
    expect(s.unit).toBe('s')
    expect(s.title).toBe('Request duration p95')
  })

  it('uses gauges as-is with a bytes unit', () => {
    const s = suggestQuery(metric({ name: 'node_memory_MemAvailable_bytes', labels: ['instance', 'job'] }))
    expect(s.expr).toBe('node_memory_MemAvailable_bytes')
    expect(s.unit).toBe('bytes')
    expect(s.legend).toBe('{{instance}}')
  })
})

describe('humanize', () => {
  it('strips exporter prefixes and units', () => {
    expect(humanize('node_filesystem_avail_bytes')).toBe('Filesystem avail')
    expect(humanize('up')).toBe('Up')
  })
})
