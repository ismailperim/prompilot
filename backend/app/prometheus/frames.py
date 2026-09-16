"""Convert Prometheus query results into the DataFrame intermediate format.

The format is modelled on Grafana data frames: a frame is a list of
same-length columns ("fields"). All renderers and the Grafana exporter
consume frames, never raw Prometheus responses, so future datasources only
need a converter into this format.

Conventions:
- timestamps are epoch **milliseconds** (ints);
- missing samples are ``None`` so every series in a matrix shares one time
  axis; ``NaN`` and ``±Inf`` also become ``None`` (JSON cannot carry them);
- a *matrix* becomes a wide frame (``time`` + one number field per series);
- a *vector* becomes a long, table-shaped frame (one row per series with a
  string field per label and a single ``value`` field).
"""

from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel

from app.models import CamelModel
from app.prometheus.client import QueryResult

FieldType = Literal["time", "number", "string"]

_LEGEND_VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class Field(BaseModel):
    name: str
    type: FieldType
    labels: dict[str, str] | None = None
    values: list[float | int | str | None]


class DataFrame(CamelModel):
    ref_id: str
    fields: list[Field]

    @property
    def length(self) -> int:
        return len(self.fields[0].values) if self.fields else 0


def parse_sample_value(raw: str | float) -> float | None:
    """Prometheus encodes samples as strings; NaN/±Inf are unrepresentable in JSON → None."""
    value = float(raw)
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def to_millis(timestamp: float) -> int:
    return round(float(timestamp) * 1000)


def render_legend(template: str | None, labels: dict[str, str]) -> str:
    """Resolve a Grafana-style legend template (``{{pod}}``) against a label set.

    Without a template the Prometheus notation ``name{a="1",b="2"}`` is used.
    Unknown labels render as an empty string, like Grafana.
    """
    if template:
        return _LEGEND_VAR.sub(lambda m: labels.get(m.group(1), ""), template).strip()

    name = labels.get("__name__", "")
    rest = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()) if k != "__name__")
    if rest:
        return f"{name}{{{rest}}}"
    return name or "value"


def to_frame(result: QueryResult, *, ref_id: str, legend: str | None = None) -> DataFrame:
    """Dispatch on ``resultType`` and build the frame for one query."""
    match result.result_type:
        case "matrix":
            return matrix_to_frame(result.result, ref_id=ref_id, legend=legend)
        case "vector":
            return vector_to_frame(result.result, ref_id=ref_id)
        case "scalar":
            return scalar_to_frame(result.result, ref_id=ref_id)
        case "string":
            return string_to_frame(result.result, ref_id=ref_id)
        case other:
            raise ValueError(f"unsupported Prometheus resultType {other!r}")


def matrix_to_frame(
    series: list[dict[str, Any]], *, ref_id: str, legend: str | None = None
) -> DataFrame:
    """Wide frame: one shared ``time`` axis, one number field per series (gaps = ``None``)."""
    timestamps: set[int] = set()
    parsed: list[tuple[dict[str, str], dict[int, float | None]]] = []
    for entry in series:
        samples = {to_millis(ts): parse_sample_value(val) for ts, val in entry.get("values", [])}
        timestamps.update(samples)
        parsed.append((dict(entry.get("metric", {})), samples))

    axis = sorted(timestamps)
    fields: list[Field] = [Field(name="time", type="time", values=list(axis))]
    for labels, samples in parsed:
        fields.append(
            Field(
                name=render_legend(legend, labels),
                type="number",
                labels=labels,
                values=[samples.get(ts) for ts in axis],
            )
        )
    return DataFrame(ref_id=ref_id, fields=fields)


def vector_to_frame(series: list[dict[str, Any]], *, ref_id: str) -> DataFrame:
    """Long frame: a row per series — ``time``, one string field per label key, ``value``."""
    label_keys = sorted({key for entry in series for key in entry.get("metric", {})})
    times: list[float | int | str | None] = []
    value_column: list[float | int | str | None] = []
    label_columns: dict[str, list[float | int | str | None]] = {key: [] for key in label_keys}

    for entry in series:
        ts, raw = entry["value"]
        times.append(to_millis(ts))
        value_column.append(parse_sample_value(raw))
        labels = entry.get("metric", {})
        for key in label_keys:
            label_columns[key].append(labels.get(key, ""))

    fields: list[Field] = [Field(name="time", type="time", values=times)]
    fields.extend(Field(name=key, type="string", values=label_columns[key]) for key in label_keys)
    fields.append(Field(name="value", type="number", values=value_column))
    return DataFrame(ref_id=ref_id, fields=fields)


def scalar_to_frame(result: list[Any], *, ref_id: str) -> DataFrame:
    ts, raw = result
    return DataFrame(
        ref_id=ref_id,
        fields=[
            Field(name="time", type="time", values=[to_millis(ts)]),
            Field(name="value", type="number", values=[parse_sample_value(raw)]),
        ],
    )


def string_to_frame(result: list[Any], *, ref_id: str) -> DataFrame:
    ts, text = result
    return DataFrame(
        ref_id=ref_id,
        fields=[
            Field(name="time", type="time", values=[to_millis(ts)]),
            Field(name="value", type="string", values=[str(text)]),
        ],
    )
