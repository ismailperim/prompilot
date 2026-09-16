# Panel spec

> Draft — finalised in milestone M2.

A panel spec is a declarative JSON document describing one panel. It is the
contract between the chat agent, the renderer and the Grafana exporter. Data
is never part of the spec.

```json
{
  "version": 1,
  "id": "uuid",
  "type": "timeseries",
  "title": "CPU Usage per Pod",
  "description": "",
  "queries": [
    { "refId": "A", "expr": "rate(container_cpu_usage_seconds_total[5m])", "legend": "{{pod}}", "instant": false }
  ],
  "unit": "percentunit",
  "options": {}
}
```

| Field | Notes |
| --- | --- |
| `version` | Schema version. Bumping it requires a migration function. |
| `type` | Registered panel type (`timeseries`, `stat`, `table`, …). |
| `queries[]` | One or more PromQL queries. `refId` follows the Grafana `A`, `B`, `C` convention. `instant: true` uses an instant query. |
| `unit` | One of the supported Grafana unit IDs: `none`, `short`, `percent`, `percentunit`, `bytes`, `decbytes`, `Bps`, `bps`, `s`, `ms`, `ops`, `reqps`, `rps`, `wps`. |
| `timeFrom` | Optional per-panel relative range override (e.g. `24h`). Maps to Grafana `timeFrom`. |
| `options` | Panel-type specific, validated by that type's schema. |

The time range itself belongs to the dashboard, not the panel.
