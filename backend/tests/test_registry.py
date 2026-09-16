from typing import Any

import pytest
from pydantic import BaseModel

from app.panels import PanelValidationError, UnknownPanelTypeError, registry
from app.panels.base import PanelModule, PanelSpec
from app.panels.registry import PanelRegistry
from tests.conftest import TIMESERIES_SPEC


def test_builtin_types_are_registered() -> None:
    assert "timeseries" in registry.types()


def test_validate_fills_defaults_and_generates_id() -> None:
    spec = registry.validate(TIMESERIES_SPEC)
    assert spec.version == 1
    assert len(spec.id) == 36
    assert spec.unit == "percentunit"
    assert spec.options == {
        "draw": "line",
        "stack": False,
        "fill": 0.0,
        "lineWidth": 1,
        "legend": "bottom",
        "min": None,
        "max": None,
    }


def test_validate_accepts_camel_and_snake_case() -> None:
    camel = registry.validate({**TIMESERIES_SPEC, "timeFrom": "24h"})
    snake = registry.validate({**TIMESERIES_SPEC, "time_from": "24h"})
    assert camel.time_from == snake.time_from == "24h"
    assert camel.model_dump()["timeFrom"] == "24h"


@pytest.mark.parametrize(
    ("patch", "expected_fragment"),
    [
        ({"type": "piechart"}, "unknown panel type 'piechart'"),
        ({"title": ""}, "title:"),
        ({"queries": []}, "queries:"),
        ({"unit": "furlongs"}, "unit:"),
        ({"timeFrom": "yesterday"}, "timeFrom:"),
        ({"queries": [{"refId": "AA", "expr": "up"}]}, "queries.0.refId"),
        ({"color": "red"}, "color: Extra inputs are not permitted"),
        ({"options": {"draw": "spline"}}, "options.draw:"),
        ({"options": {"fill": 2}}, "options.fill:"),
        ({"options": {"bogus": 1}}, "options.bogus:"),
    ],
)
def test_validation_errors_are_readable(patch: dict[str, Any], expected_fragment: str) -> None:
    with pytest.raises(PanelValidationError) as exc_info:
        registry.validate({**TIMESERIES_SPEC, **patch})
    assert any(expected_fragment in e for e in exc_info.value.errors), exc_info.value.errors


def test_unknown_type_lists_known_types() -> None:
    with pytest.raises(UnknownPanelTypeError, match="timeseries"):
        registry.validate({**TIMESERIES_SPEC, "type": "nope"})


def test_duplicate_registration_is_rejected() -> None:
    class Opts(BaseModel):
        pass

    module = PanelModule(type="x", description="", options_model=Opts, to_grafana=lambda s: {})
    reg = PanelRegistry()
    reg.register(module)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(module)


def test_spec_round_trips_through_json() -> None:
    spec = registry.validate(TIMESERIES_SPEC)
    again = PanelSpec.model_validate_json(spec.model_dump_json())
    assert again == spec
