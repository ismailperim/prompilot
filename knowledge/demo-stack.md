# Demo stack

The `docker compose` stack that ships with PromPilot. Everything here is for
trying the product; replace these notes with your own system's when you point
PromPilot at real Prometheus.

## Scrape targets

- `job="prometheus"` — Prometheus scraping itself at `localhost:9090`.
- `job="node"` — node-exporter at `node-exporter:9100`, scraped every 15 s.

`up{job="node"} == 0` means the node-exporter container is down or unreachable.

## CPU

`node_cpu_seconds_total` is a counter split by `cpu` and `mode`. Busy fraction per
core is `1 - rate(node_cpu_seconds_total{mode="idle"}[5m])`; for the whole machine
average it with `avg without (cpu)`. Values are 0–1 → unit `percentunit`.

## Memory

Use `node_memory_MemAvailable_bytes` (not `MemFree`) for "free memory": it accounts
for reclaimable cache. Used memory is `node_memory_MemTotal_bytes -
node_memory_MemAvailable_bytes`. Unit `bytes`.

## Filesystems

`node_filesystem_*` includes container-internal mounts such as `/etc/hostname`;
filter with `fstype!~"tmpfs|overlay"` and prefer `mountpoint="/"` for the root
disk. Usage ratio: `1 - node_filesystem_avail_bytes / node_filesystem_size_bytes`.

## Network

`node_network_receive_bytes_total` / `node_network_transmit_bytes_total` per
`device`. Exclude `lo` and virtual devices (`device!~"lo|veth.*|docker.*"`).
Rates are bytes per second → unit `Bps`.

## Prometheus itself

- `scrape_duration_seconds` per job shows how long each scrape takes.
- `prometheus_tsdb_head_series` is the number of active series; a sudden jump
  usually means a new high-cardinality label.

## Metric notes

- `node_load1` — 1-minute load average; compare with the core count (`count(node_cpu_seconds_total{mode="idle"})`) before calling it high.
- `node_memory_MemAvailable_bytes` — memory that can be handed out without swapping; use this, not `MemFree`.
- `scrape_duration_seconds` — how long each scrape took; a rising trend on `job="node"` usually means the exporter is struggling.
- `up` — 1 when the last scrape succeeded, 0 otherwise.
