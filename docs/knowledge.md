# Knowledge base

PromPilot's metric catalog answers "which metrics exist?". The knowledge base
answers "what do they mean here?" — the part only you know: which service a
metric belongs to, what a healthy value looks like, which labels matter, what
the SLOs are.

It is a directory of Markdown files. No UI, no database to manage: edit the
files, commit them next to your infrastructure code, mount them into the
container.

## Location

`KNOWLEDGE_DIR`, default `$DATA_DIR/knowledge` (`/data/knowledge` in the
image). The compose file mounts the repository's `knowledge/` directory there.

Files directly in that directory apply to every project. A subdirectory named
after a project's slug (`knowledge/prod-eu/`) applies to that project only;
its `prompt.md` is appended after the shared one.
Files are re-read whenever their modification time changes, so edits show up
in the next chat message. `POST /api/knowledge/reload` forces a re-read;
`GET /api/knowledge` shows what is loaded.

## `prompt.md` — standing instructions

Injected verbatim into the system prompt of every conversation, after
PromPilot's own rules. Use it for things that are always true:

```markdown
We run a Kubernetes cluster for an e-commerce platform. Namespaces map to
teams: `pay-*` is Payments, `cat-*` is Catalog.

- Latency SLOs are p99 < 300 ms for checkout, p95 < 800 ms elsewhere.
- Prefer breakdowns by `service`; never by `pod` unless asked.
- "Prod" means `cluster="eu-prod"`.
```

Keep it short — it is sent with every message.

## Other `*.md` files — searchable notes

Any other Markdown file is a document. The first `# Heading` is its title;
`##`/`###` headings split it into sections, and each section becomes a
searchable chunk (long sections are split on paragraphs).

```markdown
# Checkout service

Owned by Payments. Runs in `pay-checkout`.

## Request latency

`checkout_request_duration_seconds` is a histogram. p99 must stay under
300 ms. Use `histogram_quantile(0.99, sum by (le) (rate(..._bucket[5m])))`.

## Queue depth

`checkout_queue_depth` above 500 means workers are falling behind.
```

How the agent uses them:

1. The system prompt lists every document with its section headings, so the
   model knows what it can look up.
2. The sections best matching the user's message are added to the prompt
   before the model answers (no extra round trip).
3. The model can call `search_knowledge("queue depth alerting")` for more.

Search is full-text (SQLite FTS5): metric names, service names and plain
words all work. Write notes the way you would explain the system to a new
teammate — that is exactly what the model is.

## What to put there

- What each service is and which metrics describe it.
- Which labels to break down by, and which to aggregate away.
- Units and value ranges ("this is 0–1, not 0–100").
- SLOs, alert thresholds, and what "normal" looks like.
- Known quirks: metrics that lie, exporters with odd naming, retired metrics.

## Metric notes

Anywhere in a document, a bullet of the form

```markdown
- `node_load1` — 1-minute load average; compare with the core count before calling it high.
```

attaches that sentence to the metric. It shows up in the metric browser, in
`GET …/catalog/search` results as `note`, and in what the agent sees when it
searches the catalog — so the operator's meaning travels with the metric name.

## Playbooks

`knowledge/playbooks/*.md` (or `knowledge/<slug>/playbooks/` for one project)
are procedures the agent runs on request. The first heading is the title, the
first paragraph is the description shown in the UI, and the rest are the
steps:

```markdown
# Host health check

A quick read on whether the host is healthy.

1. Add a stat panel "Targets up" with `up` per job, colour mode background.
2. Add a stat panel "CPU busy" as a fraction, thresholds orange 0.7 / red 0.9.
3. Finish with a two-sentence summary of what is saturated or down.
```

Each playbook appears as a button above the chat composer; running one sends
its steps as the request (any text in the composer is passed along as extra
instructions). Via the API: `POST …/chat` with `{"playbook": "host-health"}`.
Write the steps the way you would brief a colleague: which panels, which
metrics or notes to prefer, what the summary should answer.
