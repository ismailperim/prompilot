# Changelog

All notable changes to PromPilot are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/).

## [Unreleased]

### Added
- Gauge panel: a dial for bounded quantities with threshold bands; exports as
  a Grafana gauge. (#17)
- Inspect a panel's data as a table, copy or download it as CSV, copy its
  PromQL; drag across a time series to zoom the dashboard to that span. (#15)
- `/metrics`: PromPilot's own Prometheus metrics — HTTP, chat outcomes, model
  turn and tool call latencies, catalog builds. The demo stack scrapes it. (#11)
- Several dashboards per project: create, rename, duplicate and delete from
  the top bar; panels can be duplicated. Dashboards live at
  `/p/<project>/d/<dashboard>`. (#14)
- Authentication: `AUTH_PASSWORD` enables a sign-in screen with signed session
  cookies; `AUTH_API_TOKEN` for scripts. (#12)
- Project Prometheus passwords are encrypted at rest with `SECRET_KEY`
  (auto-generated); existing plain-text rows are upgraded on start. (#13)

### Changed
- **API:** dashboard-scoped routes moved from `/api/projects/{slug}/…` to
  `/api/projects/{slug}/dashboards/{id}/…` (panels, data, export, chat). The
  0.1 dashboard becomes `overview` automatically.

## [0.1.0] — 2026-09-17

First public release.

### Added
- Chat agent over any OpenAI-compatible LLM: searches the metric catalog,
  dry-runs PromQL, emits validated panel specs; streams its steps as a trace.
- Panels: time series, stat, table — each a self-contained module with a
  Grafana mapper; one-click export of the dashboard as Grafana JSON.
- Metric catalog with rule-based categories, label sampling and full-text
  search; works without an LLM.
- Projects: several Prometheus sources in one instance, each with its own
  dashboard, catalog and notes; public demo servers offered for a quick start.
- Knowledge base: Markdown files and an in-app Notes editor for standing
  instructions and documents; metric notes; playbooks the agent runs on
  request; the agent saves what it learns.
- Voice: microphone and read-aloud in the browser, a hands-free voice button,
  and pluggable STT/TTS providers (OpenAI-compatible local servers, Gemini via
  a gateway, ElevenLabs).
- Light and dark themes, collapsible side panel, full-screen dashboard.

[Unreleased]: https://github.com/ismailperim/prompilot/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ismailperim/prompilot/releases/tag/v0.1.0
