# Adding a panel type

Panels are self-contained modules. Adding one never requires changing core
code, which is why this is a good first contribution. The `timeseries` panel
is the reference implementation.

## 1. Backend module — `backend/app/panels/<type>.py`

```python
from typing import Any, Literal

from pydantic import Field

from app.models import CamelModel
from app.panels.base import PanelModule, PanelSpec, grafana_panel_base


class GaugeOptions(CamelModel):
    # Keep this narrow: enums and bounded numbers. What the LLM can't express, it can't get wrong.
    min: float = 0
    max: float = 100
    thresholds: list[float] = Field(default_factory=list, max_length=5)


def to_grafana(spec: PanelSpec) -> dict[str, Any]:
    opts = GaugeOptions.model_validate(spec.options)
    panel = grafana_panel_base(spec)        # title, targets, unit, datasource
    panel["type"] = "gauge"
    panel["fieldConfig"]["defaults"].update({"min": opts.min, "max": opts.max})
    return panel


MODULE = PanelModule(
    type="gauge",
    description="A single current value on a dial. Pick for saturation-style metrics with a known bound.",
    options_model=GaugeOptions,
    to_grafana=to_grafana,
    default_layout=(6, 6),
)
```

`description` is shown to the LLM when it picks a panel type, so write it as
guidance: *when* to use this panel and what the options do.

## 2. Register it — `backend/app/panels/__init__.py`

```python
from app.panels import gauge
registry.register(gauge.MODULE)
```

## 3. Frontend renderer — `frontend/src/panels/Gauge.tsx`

```tsx
import type { PanelRendererProps } from './types'

export function Gauge({ spec, frames, timeRange }: PanelRendererProps) {
  // frames: one DataFrame per query; see docs/panel-spec.md
  return <div>…</div>
}
```

Add it to `frontend/src/panels/registry.ts`:

```ts
const renderers: Record<string, PanelRenderer> = {
  timeseries: Timeseries,
  gauge: Gauge,
}
```

Renderers run inside an error boundary, so a bug shows an error in that
panel only. Format values with `formatValue(value, spec.unit)` from
`src/format/units.ts`.

## 4. Tests

- `backend/tests/test_panel_<type>.py`: options round-trip (defaults are
  filled in, invalid values are rejected) and a Grafana JSON golden snapshot
  in `backend/tests/snapshots/grafana/`. Run once with `UPDATE_SNAPSHOTS=1`
  to create it, then review the file.
- A vitest for any pure option-building logic on the frontend.

## 5. Verify in Grafana

`docker compose --profile grafana up -d`, add a panel of the new type,
**Export to Grafana**, and import the file at <http://localhost:3000>
(*Dashboards → New → Import*). The exported panel should look like the
PromPilot one.
