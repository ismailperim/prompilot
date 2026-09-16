# PromPilot

**Chat-driven Prometheus visualization with one-click Grafana export.**

PromPilot connects to your Prometheus, discovers your metrics, and lets you
build charts by asking for them in plain language. Every panel it creates can
be exported as a Grafana dashboard. It runs as a single Docker container with
no cloud dependency — bring your own LLM, including local ones via Ollama or
vLLM.

> **Status:** early development. Not ready for production use yet — follow the
> [milestones](#roadmap) below.

<!-- TODO: demo GIF -->

## Why

Grafana is great at rendering dashboards, but building them still means
knowing which of your 5,000 metrics to pick and how to write the PromQL.
PromPilot adds a conversational layer on top:

- **Metric catalog** — metrics are discovered, categorised and indexed
  automatically, so "show me CPU per core" finds `node_cpu_seconds_total`
  without you memorising exporter names. Works without an LLM.
- **Chat → panel** — ask for a chart; the LLM picks the metric, writes and
  dry-runs the PromQL, and emits a validated panel spec. Rendering is
  deterministic — the model never writes chart code.
- **Grafana export** — download the resulting dashboard as Grafana JSON and
  import it. PromPilot is an add-on layer, not a replacement.

## Quick start

```bash
docker run -d -p 8080:8080 \
  -e PROMETHEUS_URL=http://your-prometheus:9090 \
  -e LLM_BASE_URL=http://ollama:11434/v1 \
  -e LLM_MODEL=llama3.1 \
  -v prompilot-data:/data \
  ghcr.io/OWNER/prompilot:latest
```

Open <http://localhost:8080>.

Don't have a Prometheus handy? The repository ships a demo stack with
Prometheus and node-exporter:

```bash
git clone https://github.com/OWNER/prompilot.git
cd prompilot
docker compose up -d
```

Add `--profile grafana` to also start Grafana (for testing exports) or
`--profile ollama` for a local LLM.

## Configuration

All configuration is via environment variables.

| Variable | Default | Description |
| --- | --- | --- |
| `PROMETHEUS_URL` | — | **Required.** Base URL of your Prometheus (or compatible: Thanos, Mimir, VictoriaMetrics). |
| `PROMETHEUS_USERNAME` / `PROMETHEUS_PASSWORD` | — | Optional basic auth. |
| `PROMETHEUS_QUERY_TIMEOUT` | `30s` | Timeout applied to every Prometheus call. |
| `PROMETHEUS_MAX_DATA_POINTS` | `1000` | Upper bound on points per series; the query step is derived from it. |
| `LLM_BASE_URL` | — | Any OpenAI-compatible endpoint (OpenAI, Ollama, vLLM, LM Studio, OpenRouter…). Chat is disabled when unset. |
| `LLM_MODEL` | — | Model name, e.g. `gpt-4o-mini`, `llama3.1`, `qwen2.5`. |
| `LLM_API_KEY` | — | API key; optional for local endpoints. |
| `LLM_TIMEOUT` | `60s` | Timeout for LLM requests. |
| `CATALOG_LLM_ENRICH` | `false` | Use the LLM to categorise metrics the built-in rules can't. |
| `CATALOG_REBUILD_INTERVAL` | `24h` | Periodic catalog rebuild; `0` disables. |
| `DATA_DIR` | `/data` | SQLite storage (catalog + dashboard). Mount a volume. |
| `PORT` | `8080` | HTTP port. |
| `LOG_LEVEL` | `info` | Log level. |

## Security

PromPilot has **no built-in authentication**. Run it on a trusted network or
behind an authenticating reverse proxy. Chat messages and metric metadata are
sent to the LLM endpoint you configure. See [SECURITY.md](SECURITY.md).

## Roadmap

- [x] M0 — Project skeleton, Docker image, demo compose stack, CI
- [ ] M1 — Prometheus client and data-frame layer
- [ ] M2 — Panel registry, time-series panel, dashboard grid
- [ ] M3 — Grafana dashboard export
- [ ] M4 — Metric catalog with full-text search
- [ ] M5 — Chat agent
- [ ] M6 — Stat and table panels, auto-refresh
- [ ] M7 — Polish and first release

Planned later: gauge/bar/heatmap panels, multiple dashboards, additional
datasources (Loki, VictoriaMetrics), native cloud LLM SDKs, more Prometheus
auth methods.

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the
development setup. Adding a new panel type is a self-contained change and a
great first issue; see [docs/adding-a-panel.md](docs/adding-a-panel.md).

## License

[Apache License 2.0](LICENSE)
