"""Validate / render tests for gantt, stack_bar, waterfall, cost_breakdown, image_slot."""

from __future__ import annotations

import re

from render.figure_renderers import list_capabilities, renderer_for
from render.figure_renderers.base import EMUBox, RenderContext
from render.shapes import DEFAULT_FONT, DEFAULT_PALETTE

_OFF_EXT_RE = re.compile(r'<a:(?:off|ext)\s+(?:x|y|cx|cy)="([^"]+)"')
_NEW_TYPES = ("gantt", "stack_bar", "waterfall", "cost_breakdown", "image_slot")


def _ctx() -> RenderContext:
    return RenderContext(palette=DEFAULT_PALETTE, font=DEFAULT_FONT, next_shape_id=1000)


def _box() -> EMUBox:
    return EMUBox(x=457200, y=1463040, w=11246400, h=4937760)


def _assert_int_emu(shapes_xml: list[str]) -> None:
    for xml in shapes_xml:
        for raw in _OFF_EXT_RE.findall(xml):
            assert raw.lstrip("-").isdigit(), f"non-integer EMU coord: {raw!r}"


def test_batch3_types_listed_in_capabilities() -> None:
    ftypes = {c["figure_type"] for c in list_capabilities()}
    for expected in _NEW_TYPES:
        assert expected in ftypes


def test_gantt_registry_lookup() -> None:
    r = renderer_for("gantt")
    assert r.figure_type == "gantt"


def test_gantt_rejects_missing_fields() -> None:
    r = renderer_for("gantt")
    assert not r.validate({}).ok
    assert not r.validate({"tasks": [], "total_weeks": 4}).ok
    assert not r.validate({"tasks": [{"label": "A"}], "total_weeks": 4}).ok
    assert not r.validate(
        {"tasks": [{"label": "A", "start_week": 2, "end_week": 1}], "total_weeks": 4}
    ).ok
    assert not r.validate({"tasks": [{"label": "A", "start_week": 0, "end_week": 1}]}).ok


def test_gantt_renders() -> None:
    r = renderer_for("gantt")
    content = {
        "total_weeks": 6,
        "tasks": [
            {"label": "Design", "start_week": 0, "end_week": 2, "group": "A"},
            {"label": "Build", "start_week": 2, "end_week": 5, "group": "B"},
            {"label": "Ship", "start_week": 5, "end_week": 6, "group": "A"},
        ],
        "milestones": [{"label": "Launch", "week": 6}],
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    assert out.next_shape_id > 1000
    _assert_int_emu(out.shapes_xml)


def test_stack_bar_registry_lookup() -> None:
    r = renderer_for("stack_bar")
    assert r.figure_type == "stack_bar"


def test_stack_bar_rejects_missing_fields() -> None:
    r = renderer_for("stack_bar")
    assert not r.validate({}).ok
    assert not r.validate({"categories": [], "series": []}).ok
    assert not r.validate(
        {"categories": ["Q1", "Q2"], "series": [{"name": "A", "values": [1]}]}
    ).ok
    assert not r.validate(
        {"categories": ["Q1"], "series": [{"values": [1]}]}
    ).ok
    assert not r.validate(
        {
            "categories": [f"c{i}" for i in range(7)],
            "series": [{"name": "A", "values": [1] * 7}],
        }
    ).ok


def test_stack_bar_renders() -> None:
    r = renderer_for("stack_bar")
    content = {
        "categories": ["Q1", "Q2", "Q3"],
        "series": [
            {"name": "Product", "values": [30, 40, 50]},
            {"name": "Services", "values": [10, 20, 15]},
        ],
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    _assert_int_emu(out.shapes_xml)


def test_waterfall_registry_lookup() -> None:
    r = renderer_for("waterfall")
    assert r.figure_type == "waterfall"


def test_waterfall_rejects_missing_fields() -> None:
    r = renderer_for("waterfall")
    assert not r.validate({}).ok
    assert not r.validate(
        {"start": {"label": "S", "value": 100}, "changes": [], "end": {"label": "E"}}
    ).ok
    assert not r.validate(
        {
            "start": {"label": "S"},
            "changes": [{"label": "X", "value": 1}],
            "end": {"label": "E"},
        }
    ).ok
    assert not r.validate(
        {
            "start": {"label": "S", "value": 100},
            "changes": [{"label": "X", "value": 1}],
        }
    ).ok


def test_waterfall_renders() -> None:
    r = renderer_for("waterfall")
    content = {
        "start": {"label": "FY23", "value": 1000},
        "changes": [
            {"label": "Growth", "value": 200},
            {"label": "Churn", "value": -80},
            {"label": "Expansion", "value": 150},
        ],
        "end": {"label": "FY24"},
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    _assert_int_emu(out.shapes_xml)


def test_cost_breakdown_registry_lookup() -> None:
    r = renderer_for("cost_breakdown")
    assert r.figure_type == "cost_breakdown"


def test_cost_breakdown_rejects_missing_fields() -> None:
    r = renderer_for("cost_breakdown")
    assert not r.validate({}).ok
    assert not r.validate({"total": {"label": "T", "amount": 100}, "items": []}).ok
    assert not r.validate(
        {"total": {"label": "T"}, "items": [{"label": "A", "amount": 10}]}
    ).ok
    assert not r.validate(
        {"total": {"label": "T", "amount": 100}, "items": [{"label": "A"}]}
    ).ok


def test_cost_breakdown_renders() -> None:
    r = renderer_for("cost_breakdown")
    content = {
        "total": {"label": "Total Cost", "amount": 125000, "currency": "¥"},
        "items": [
            {"label": "Labor", "amount": 60000},
            {"label": "Infra", "amount": 40000},
            {"label": "Tools", "amount": 25000},
        ],
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    _assert_int_emu(out.shapes_xml)


def test_image_slot_registry_lookup() -> None:
    r = renderer_for("image_slot")
    assert r.figure_type == "image_slot"


def test_image_slot_rejects_missing_fields() -> None:
    r = renderer_for("image_slot")
    assert not r.validate({}).ok
    assert not r.validate({"asset_id": ""}).ok
    assert not r.validate({"asset_id": "  "}).ok
    assert not r.validate({"asset_id": "abc", "fit": "bogus"}).ok
    assert not r.validate({"asset_id": "abc", "caption": 123}).ok


def test_image_slot_renders_stub() -> None:
    r = renderer_for("image_slot")
    content = {
        "asset_id": "abc12345def67890",
        "caption": "A diagram",
        "alt": "Flow diagram",
        "fit": "contain",
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    _assert_int_emu(out.shapes_xml)
