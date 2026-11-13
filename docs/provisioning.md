# Provisioning projects from a file

Projects are usually created in the UI. When PromPilot is deployed by
Kubernetes, Ansible or any GitOps workflow, you can declare them in a YAML file
instead and point `PROJECTS_FILE` at it:

```yaml
# projects.yaml
projects:
  # Prometheus reached directly
  - slug: staging
    name: Staging
    prometheusUrl: http://prometheus.staging:9090

  # Prometheus reached through a Grafana datasource (see "Through Grafana" in the README)
  - slug: prod-eu
    name: Production EU
    source: grafana
    grafanaUrl: https://grafana.example.com
    grafanaDatasourceUid: mimir-eu
    username: prompilot
    password: ${PROD_EU_GRAFANA_PASSWORD}

  # Basic auth and a self-signed certificate
  - slug: lab
    prometheusUrl: https://prometheus.lab.example.com
    username: reader
    password: ${LAB_PROMETHEUS_PASSWORD}
    tlsVerify: false
```

```sh
docker run -p 8080:8080 \
  -v ./projects.yaml:/etc/prompilot/projects.yaml:ro \
  -e PROJECTS_FILE=/etc/prompilot/projects.yaml \
  -e PROD_EU_GRAFANA_PASSWORD=… -e LAB_PROMETHEUS_PASSWORD=… \
  -v prompilot-data:/data ghcr.io/ismailperim/prompilot
```

## Fields

| Field | Required | Description |
| --- | --- | --- |
| `slug` | yes | Project id used in URLs (`/p/<slug>`): lowercase letters, digits and dashes. Use `default` to manage the project created on first start. |
| `name` | no | Display name; defaults to the slug. |
| `source` | no | `prometheus` (default) or `grafana`. |
| `prometheusUrl` | for `prometheus` | Prometheus (or Thanos, Mimir, VictoriaMetrics) base URL. |
| `grafanaUrl` | for `grafana` | Grafana base URL. |
| `grafanaDatasourceUid` | for `grafana` | UID of a Prometheus-type datasource in that Grafana (shown in the datasource's URL, or listed by **Find datasources** in the project dialog). |
| `username` / `password` | no | Basic auth for Prometheus, or for Grafana when `source: grafana`. |
| `tlsVerify` | no | Verify the TLS certificate; defaults to `PROMETHEUS_TLS_VERIFY`. |

Keys may also be written in snake_case (`prometheus_url`). Unknown keys are
rejected, so a typo fails loudly instead of being ignored.

## Secrets

Any value may reference an environment variable as `${NAME}`, so the file can
be committed or stored in a ConfigMap while passwords come from a Secret. A
reference to an unset variable is an error. A `$` not followed by `{` is kept
as is.

## How it is applied

- The file is read on every start. An invalid file stops startup with a message
  that names the offending entry; values are never echoed, so secrets do not
  end up in logs.
- Listed projects are created, or updated to match the file. Their
  dashboards, chat transcripts, catalog and notes are left alone.
- Listed projects are **managed**: the project dialog shows their connection
  settings read-only, and the API answers `409` to edits or deletion. Change
  the file and restart instead. Everything inside the project — dashboards,
  panels, notes — stays editable.
- A project removed from the file is **not deleted**; it simply stops being
  managed and becomes editable in the UI again. Delete it there if you no
  longer need it. Unsetting `PROJECTS_FILE` releases every managed project.
- On a fresh install with a projects file, no extra `default` project is
  created from `PROMETHEUS_URL` / `GRAFANA_URL`.
- Passwords are stored encrypted with `SECRET_KEY`, like those entered in the
  UI. If the key changes, the next start re-encrypts managed passwords from the
  file.
