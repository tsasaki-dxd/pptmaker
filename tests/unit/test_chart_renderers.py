"""Validate / render tests for bar_chart, line_chart, pie_chart figure_types."""

from __future__ import annotations

import re

from render.figure_renderers import list_capabilities, renderer_for
from render.figure_renderers.base import EMUBox, RenderContext
from render.shapes import DEFAULT_FONT, DEFAULT_PALETTE

_OFF_EXT_RE = re.compile(r'<a:(?:off|ext)\s+(?:x|y|cx|cy)="([^"]+)"')
_NEW_TYPES = ("bar_chart", "line_chart", "pie_chart")


def _ctx() -> RenderContext:
    return RenderContext(palette=DEFAULT_PALETTE, font=DEFAULT_FONT, next_shape_id=1000)


def _box() -> EMUBox:
    return EMUBox(x=457200, y=1463040, w=11246400, h=4937760)


def _assert_int_emu(shapes_xml: list[str]) -> None:
    for xml in shapes_xml:
        for raw in _OFF_EXT_RE.findall(xml):
            assert raw.lstrip("-").isdigit(), f"non-integer EMU coord: {raw!r}"


def test_chart_types_listed_in_capabilities() -> None:
    ftypes = {c["figure_type"] for c in list_capabilities()}
    for expected in _NEW_TYPES:
        assert expected in ftypes


# -------------------- bar_chart -------------------------------------------


def test_bar_chart_registry_lookup() -> None:
    r = renderer_for("bar_chart")
    assert r.figure_type == "bar_chart"


def test_bar_chart_rejects_missing_fields() -> None:
    r = renderer_for("bar_chart")
    # Neither items nor series.
    assert not r.validate({}).ok
    # Both items and series.
    assert not r.validate({
        "items": [{"label": "A", "value": 1}],
        "series": [{"name": "X", "values": [1]}],
        "categories": ["Q1"],
    }).ok
    # series without categories.
    assert not r.validate({"series": [{"name": "X", "values": [1, 2]}]}).ok
    # values length mismatch.
    assert not r.validate({
        "categories": ["Q1", "Q2"],
        "series": [{"name": "X", "values": [1]}],
    }).ok
    # bad mode.
    assert not r.validate({
        "items": [{"label": "A", "value": 1}],
        "mode": "stacked999",
    }).ok


def test_bar_chart_single_series_renders() -> None:
    r = renderer_for("bar_chart")
    content = {
        "items": [
            {"label": "Q1", "value": 100},
            {"label": "Q2", "value": 120},
            {"label": "Q3", "value": 95},
        ],
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    _assert_int_emu(out.shapes_xml)


def test_bar_chart_multi_series_renders() -> None:
    r = renderer_for("bar_chart")
    content = {
        "categories": ["FY22", "FY23", "FY24"],
        "series": [
            {"name": "売上", "values": [100, 110, 120]},
            {"name": "粗利", "values": [30, 35, 42]},
        ],
        "mode": "grouped",
        "orientation": "v",
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    _assert_int_emu(out.shapes_xml)


# -------------------- line_chart ------------------------------------------


def test_line_chart_registry_lookup() -> None:
    r = renderer_for("line_chart")
    assert r.figure_type == "line_chart"


def test_line_chart_rejects_missing_fields() -> None:
    r = renderer_for("line_chart")
    assert not r.validate({}).ok
    # series without values.
    assert not r.validate({"series": [{"name": "X"}]}).ok
    # series with too few points (< 2).
    assert not r.validate({"series": [{"name": "X", "values": [1]}]}).ok
    # too many series.
    assert not r.validate({
        "series": [{"name": f"S{i}", "values": [1, 2]} for i in range(6)],
    }).ok


def test_line_chart_renders() -> None:
    r = renderer_for("line_chart")
    content = {
        "categories": ["Jan", "Feb", "Mar", "Apr"],
        "series": [
            {"name": "売上", "values": [100, 112, 125, 138]},
            {"name": "粗利", "values": [30, 35, 40, 46]},
        ],
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    _assert_int_emu(out.shapes_xml)


# -------------------- pie_chart -------------------------------------------


def test_pie_chart_registry_lookup() -> None:
    r = renderer_for("pie_chart")
    assert r.figure_type == "pie_chart"


def test_pie_chart_rejects_missing_fields() -> None:
    r = renderer_for("pie_chart")
    assert not r.validate({}).ok
    # Empty slices.
    assert not r.validate({"slices": []}).ok
    # Missing label / non-numeric value.
    assert not r.validate({"slices": [{"value": 10}]}).ok
    assert not r.validate({"slices": [{"label": "A", "value": "ten"}]}).ok
    # Non-positive value.
    assert not r.validate({"slices": [{"label": "A", "value": 0}]}).ok
    assert not r.validate({"slices": [{"label": "A", "value": -5}]}).ok


def test_pie_chart_renders_with_legend() -> None:
    r = renderer_for("pie_chart")
    content = {
        "slices": [
            {"label": "サブスク", "value": 60},
            {"label": "従量", "value": 25},
            {"label": "コンサル", "value": 15},
        ],
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    # 1 pie + (3 swatches + 3 labels + 3 percentages) = 10 shapes.
    assert len(out.shapes_xml) >= 4
    _assert_int_emu(out.shapes_xml)
    # Verify the percentage label was actually computed.
    joined = "\n".join(out.shapes_xml)
    assert "60%" in joined  # 60/100 of the total
