from typing import Any

import pytest

from app.prometheus import QueryResult, to_frame
from app.prometheus.frames import parse_sample_value, render_legend


def result_from(fixture_body: dict[str, Any]) -> QueryResult:
    data = fixture_body["data"]
    return QueryResult(
        result_type=data["resultType"],
        result=data["result"],
        warnings=fixture_body.get("warnings", []),
    )


class TestMatrix:
    def test_recorded_matrix_becomes_wide_frame(self, fixture: Any) -> None:
        frame = to_frame(result_from(fixture("matrix")), ref_id="A", legend="cpu {{cpu}}")

        assert frame.ref_id == "A"
        assert [f.type for f in frame.fields] == ["time", "number", "number"]
        assert [f.name for f in frame.fields] == ["time", "cpu 0", "cpu 1"]
        assert frame.fields[1].labels == {
            "cpu": "0",
            "instance": "node-exporter:9100",
            "job": "node",
            "mode": "idle",
        }
        assert all(len(f.values) == frame.length for f in frame.fields)

    def test_series_are_aligned_on_a_shared_axis_with_null_gaps(self, fixture: Any) -> None:
        frame = to_frame(result_from(fixture("matrix_gaps")), ref_id="A", legend="{{instance}}")

        time, a, b = frame.fields
        assert time.values == [1700000000000, 1700000030000, 1700000060000, 1700000090000]
        assert a.values == [1.0, 1.0, 0.0, None]
        # NaN and +Inf are not JSON-representable → None
        assert b.values == [1.0, None, None, None]

    def test_empty_matrix_yields_only_an_empty_time_axis(self, fixture: Any) -> None:
        frame = to_frame(result_from(fixture("empty_matrix")), ref_id="A")
        assert [f.name for f in frame.fields] == ["time"]
        assert frame.length == 0

    def test_default_legend_uses_prometheus_notation(self, fixture: Any) -> None:
        frame = to_frame(result_from(fixture("matrix_gaps")), ref_id="A")
        assert frame.fields[1].name == 'up{instance="a:9100",job="node"}'


class TestVector:
    def test_recorded_vector_becomes_table_shaped_frame(self, fixture: Any) -> None:
        frame = to_frame(result_from(fixture("vector")), ref_id="A")

        names = [f.name for f in frame.fields]
        assert names[0] == "time"
        assert names[-1] == "value"
        assert "device" in names and "mountpoint" in names and "__name__" in names
        assert frame.fields[0].type == "time"
        assert frame.fields[-1].type == "number"
        assert all(f.type == "string" for f in frame.fields[1:-1])
        assert frame.length == len(fixture("vector")["data"]["result"])

    def test_missing_labels_become_empty_strings(self) -> None:
        result = QueryResult(
            result_type="vector",
            result=[
                {"metric": {"a": "1", "b": "2"}, "value": [1700000000, "1"]},
                {"metric": {"a": "3"}, "value": [1700000000, "2"]},
            ],
        )
        frame = to_frame(result, ref_id="B")
        by_name = {f.name: f.values for f in frame.fields}
        assert by_name["a"] == ["1", "3"]
        assert by_name["b"] == ["2", ""]
        assert by_name["value"] == [1.0, 2.0]

    def test_empty_vector(self, fixture: Any) -> None:
        frame = to_frame(result_from(fixture("empty_vector")), ref_id="A")
        assert [f.name for f in frame.fields] == ["time", "value"]
        assert frame.length == 0


def test_scalar(fixture: Any) -> None:
    frame = to_frame(result_from(fixture("scalar")), ref_id="A")
    assert [f.name for f in frame.fields] == ["time", "value"]
    assert frame.fields[0].values == [1789565476689]
    assert frame.fields[1].values == [2.0]


def test_string() -> None:
    frame = to_frame(QueryResult(result_type="string", result=[1700000000, "hi"]), ref_id="A")
    assert frame.fields[1].type == "string"
    assert frame.fields[1].values == ["hi"]


def test_unknown_result_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        to_frame(QueryResult(result_type="blob", result=[]), ref_id="A")


def test_frame_serialises_with_camel_case_ref_id(fixture: Any) -> None:
    frame = to_frame(result_from(fixture("scalar")), ref_id="A")
    dumped = frame.model_dump(by_alias=True)
    assert dumped["refId"] == "A"
    assert "ref_id" not in dumped


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", 1.0), ("0.5", 0.5), ("-3", -3.0), ("NaN", None), ("+Inf", None), ("-Inf", None)],
)
def test_parse_sample_value(raw: str, expected: float | None) -> None:
    assert parse_sample_value(raw) == expected


@pytest.mark.parametrize(
    ("template", "labels", "expected"),
    [
        ("{{pod}}", {"pod": "api-1"}, "api-1"),
        ("{{ pod }} / {{node}}", {"pod": "api-1", "node": "n1"}, "api-1 / n1"),
        ("{{missing}}", {"pod": "api-1"}, ""),
        (None, {"__name__": "up", "job": "x", "a": "1"}, 'up{a="1",job="x"}'),
        (None, {"__name__": "up"}, "up"),
        (None, {"job": "x"}, '{job="x"}'),
        (None, {}, "value"),
    ],
)
def test_render_legend(template: str | None, labels: dict[str, str], expected: str) -> None:
    assert render_legend(template, labels) == expected
