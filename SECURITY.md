# Security Policy

## Supported versions

PromPilot is pre-1.0. Only the latest release on `main` receives security fixes.

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Use GitHub's private vulnerability reporting ("Report a vulnerability" under the
Security tab of the repository). You should receive an acknowledgement within
72 hours. We will work with you on a fix and coordinated disclosure.

## Deployment notes

- PromPilot ships **without authentication**. Run it on a private network or
  behind an authenticating reverse proxy. Never expose it directly to the
  internet.
- The chat feature forwards your questions and metric metadata to the LLM
  endpoint you configure. When using a hosted provider, review its data policy.
- `LLM_API_KEY` and the voice/ElevenLabs keys are read from the environment
  only and are never logged or returned by any API endpoint.
- Prometheus basic-auth passwords entered for projects are stored in the
  SQLite database under `DATA_DIR` **unencrypted** (the API never returns
  them). Protect the data volume accordingly; encryption at rest is planned.
- The assistant can only reach Prometheus through its read-only HTTP API. It
  cannot run code or fetch arbitrary URLs. It can write to the project's
  notes (`save_note`); those notes are visible and editable in the Notes tab.
