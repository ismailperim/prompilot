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
- `LLM_API_KEY` and `PROMETHEUS_PASSWORD` are read from the environment only
  and are never logged or returned by any API endpoint.
