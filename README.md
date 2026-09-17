<p align="center">
  <img src="docs/assets/logo.svg#gh-dark-mode-only" alt="PromPilot" width="260">
  <img src="docs/assets/logo-light.svg#gh-light-mode-only" alt="PromPilot" width="260">
</p>

<p align="center"><strong>Chat-driven Prometheus visualization with one-click Grafana export.</strong></p>

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
| `PROMETHEUS_URL` | — | Prometheus (or Thanos/Mimir/VictoriaMetrics) for the first project, created on first start. Optional once projects exist. |
| `PROMETHEUS_USERNAME` / `PROMETHEUS_PASSWORD` | — | Optional basic auth. |
| `PROMETHEUS_QUERY_TIMEOUT` | `30s` | Timeout applied to every Prometheus call. |
| `PROMETHEUS_MAX_DATA_POINTS` | `1000` | Upper bound on points per series; the query step is derived from it. |
| `LLM_BASE_URL` | — | Any OpenAI-compatible endpoint (OpenAI, Ollama, vLLM, LM Studio, OpenRouter…). Chat is disabled when unset. |
| `LLM_MODEL` | — | Model name, e.g. `gpt-4o-mini`, `llama3.1`, `qwen2.5`. |
| `LLM_API_KEY` | — | API key; optional for local endpoints. |
| `LLM_TIMEOUT` | `120s` | Timeout for a single LLM request. |
| `LLM_MAX_TOKENS` | `4096` | Completion budget per model turn. Raise it for reasoning models that think before answering. |
| `LLM_TEMPERATURE` | `0.2` | Sampling temperature. |
| `LLM_EXTRA_BODY` | — | JSON merged into every request for vendor-specific options, e.g. `{"chat_template_kwargs":{"enable_thinking":false}}` to turn off Qwen thinking on vLLM. |
| `LLM_MAX_TOOL_ITERATIONS` | `8` | Cap on tool-call rounds per message; the last round must answer in text. |
| `CATALOG_LLM_ENRICH` | `false` | Use the LLM to categorise metrics the built-in rules can't. |
| `CATALOG_REBUILD_INTERVAL` | `24h` | Periodic catalog rebuild; `0` disables. |
| `CATALOG_LABEL_SAMPLE_LIMIT` | `2000` | Max metrics whose label keys are sampled per build (the rest are sampled on demand). |
| `CATALOG_CONCURRENCY` | `6` | Parallel Prometheus calls during a catalog build. |
| `KNOWLEDGE_DIR` | `$DATA_DIR/knowledge` | Markdown notes about your system for the agent (see below). |
| `DATA_DIR` | `/data` | SQLite storage (catalog + dashboard). Mount a volume. |
| `PORT` | `8080` | HTTP port. |
| `LOG_LEVEL` | `info` | Log level. |

## Projects

One PromPilot instance can watch several Prometheus servers. Each **project**
is one Prometheus source with its own dashboard, metric catalog and notes;
switch between them from the project menu in the top bar, or address one
directly at `/p/<slug>`. Projects are created and edited in the UI (name,
URL, optional basic auth, with a connection test) or via `/api/projects`.
The `PROMETHEUS_URL` environment variable creates the first project,
`default`, on first start.

Per-project notes live in `knowledge/<slug>/`; files directly in `knowledge/`
are shared by every project.

## Teaching it your system

The agent knows what a metric is called; it doesn't know what it *means* to
you. Put Markdown notes in the `knowledge/` directory (mounted into the
container as `/data/knowledge`) and they become part of the agent's context:

- `knowledge/prompt.md` — standing instructions, injected into every
  conversation: which team owns what, SLOs, preferred breakdowns, house rules.
- any other `knowledge/*.md` — notes split by heading and indexed for search.
  The agent searches them with `search_knowledge`, and the sections matching
  your question are added to the prompt automatically.

- `- \`metric_name\` — meaning` bullets attach a note to a metric; it shows
  in the metric browser and in what the agent sees.
- `knowledge/playbooks/*.md` — procedures the agent runs on request ("Host
  health check": four panels and a two-sentence verdict). They appear as
  buttons above the chat composer.

Files are re-read whenever they change; no restart needed. The repository
ships notes and a playbook for the demo stack as an example. See
[docs/knowledge.md](docs/knowledge.md).

## Voice

The composer has a microphone (speech → text, sent when you pause) and a
speaker toggle that reads answers aloud. Both use the browser's Web Speech
API — nothing leaves the browser except the resulting text, and no extra
service is needed. Speech recognition works in Chrome, Edge and Safari.

## How the chat works

The model never draws anything. It works through a small set of tools —
`search_catalog`, `query_prometheus`, `emit_panel`, `patch_panel`,
`remove_panel` — and every panel it emits is validated against the panel
schema before it reaches the grid. If validation fails, the errors go back to
the model and it corrects the spec. The steps are shown in the chat as they
happen, so you can see which metrics it looked at and which PromQL it tested.

Any model that supports OpenAI-style function calling works. Tested with
DeepSeek and Qwen served by vLLM; Ollama and OpenAI-compatible gateways use
the same settings. Reasoning models are supported (their thinking is shown
collapsed); give them a larger `LLM_MAX_TOKENS` or disable thinking via
`LLM_EXTRA_BODY`.

## Security

PromPilot has **no built-in authentication**. Run it on a trusted network or
behind an authenticating reverse proxy. Chat messages and metric metadata are
sent to the LLM endpoint you configure. See [SECURITY.md](SECURITY.md).

## Roadmap

- [x] M0 — Project skeleton, Docker image, demo compose stack, CI
- [x] M1 — Prometheus client and data-frame layer
- [x] M2 — Panel registry, time-series panel, dashboard grid
- [x] M3 — Grafana dashboard export
- [x] M4 — Metric catalog with full-text search
- [x] M5 — Chat agent
- [x] M6 — Stat and table panels, auto-refresh
- [ ] M7 — Polish and first release

Planned later: gauge/bar/heatmap panels, multiple dashboards, additional
datasources (Loki, VictoriaMetrics), native cloud LLM SDKs, more Prometheus
auth methods.

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the
development setup. Adding a new panel type is a self-contained change and a
great first issue; see [docs/adding-a-panel.md](docs/adding-a-panel.md).

## Acknowledgements

Icons by [Lucide](https://lucide.dev) (ISC). Typeface: [IBM Plex](https://github.com/IBM/plex)
(OFL), bundled — the app makes no requests to third-party servers.

## License

[Apache License 2.0](LICENSE)
