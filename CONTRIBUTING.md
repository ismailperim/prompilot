# Contributing to PromPilot

Thanks for your interest! This document explains how to get a development
environment running and what we expect from contributions.

## Development setup

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22+,
Docker (for the demo stack).

```bash
git clone https://github.com/<org>/prompilot.git
cd prompilot

# Demo Prometheus + node-exporter on localhost:9090
docker compose up -d prometheus node-exporter

# Backend (http://localhost:8080)
cd backend
uv sync
DATA_DIR=./data PROMETHEUS_URL=http://localhost:9090 uv run uvicorn app.main:app --reload --port 8080

# Frontend (http://localhost:5173, proxies /api to :8080)
cd ../frontend
npm install
npm run dev
```

## Checks

Run these before opening a pull request — CI runs the same commands:

```bash
# backend
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest

# frontend
cd frontend && npm run lint && npm run typecheck && npm test
```

## Pull requests

- Open an issue first for anything beyond a small fix so we can agree on the
  approach.
- Keep PRs focused; one logical change per PR.
- Add or update tests for behaviour you change.
- Follow the existing code style; `ruff` and `oxlint` are the source of truth.
- Use clear commit messages (imperative mood: "Add stat panel", not "Added").

## Adding a panel type

Panels are self-contained modules — the core never needs to change. See
[`docs/adding-a-panel.md`](docs/adding-a-panel.md) for the step-by-step guide.
This is the best place to start if you're looking for a first contribution.

## License

By contributing you agree that your contributions will be licensed under the
[Apache License 2.0](LICENSE).
