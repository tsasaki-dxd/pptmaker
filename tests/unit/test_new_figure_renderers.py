"""Validate / render tests for matrix_2x2, swot, pyramid renderers."""

from __future__ import annotations

import re

from render.figure_renderers import list_capabilities, renderer_for
from render.figure_renderers.base import EMUBox, RenderContext
from render.shapes import DEFAULT_FONT, DEFAULT_PALETTE

_OFF_EXT_RE = re.compile(r'<a:(?:off|ext)\s+(?:x|y|cx|cy)="([^"]+)"')


def _ctx() -> RenderContext:
    return RenderContext(palette=DEFAULT_PALETTE, font=DEFAULT_FONT, next_shape_id=1000)


def _box() -> EMUBox:
    return EMUBox(x=457200, y=1463040, w=11246400, h=4937760)


def _assert_int_emu(shapes_xml: list[str]) -> None:
    for xml in shapes_xml:
        for raw in _OFF_EXT_RE.findall(xml):
            assert raw.lstrip("-").isdigit(), f"non-integer EMU coord: {raw!r}"


def test_new_renderers_listed_in_capabilities() -> None:
    ftypes = {c["figure_type"] for c in list_capabilities()}
    for expected in ("matrix_2x2", "swot", "pyramid"):
        assert expected in ftypes


def test_matrix_2x2_registry_lookup() -> None:
    r = renderer_for("matrix_2x2")
    assert r.figure_type == "matrix_2x2"


def test_matrix_2x2_rejects_missing_fields() -> None:
    r = renderer_for("matrix_2x2")
    assert not r.validate({}).ok
    assert not r.validate({"axes": {"x": {"label": "X"}, "y": {"label": "Y"}}}).ok
    assert not r.validate(
        {
            "axes": {"x": {"label": "X"}, "y": {"label": "Y"}},
            "quadrants": [{"title": "A"}, {"title": "B"}, {"title": "C"}],
        }
    ).ok
    assert not r.validate(
        {
            "axes": {"x": {}, "y": {"label": "Y"}},
            "quadrants": [{"title": f"Q{i}"} for i in range(4)],
        }
    ).ok


def test_matrix_2x2_renders() -> None:
    r = renderer_for("matrix_2x2")
    content = {
        "axes": {"x": {"label": "影響度"}, "y": {"label": "実行容易性"}},
        "quadrants": [
            {"title": "Q1", "body": "優先"},
            {"title": "Q2"},
            {"title": "Q3", "body": "要検討"},
            {"title": "Q4"},
        ],
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 4
    assert out.next_shape_id > 1000
    _assert_int_emu(out.shapes_xml)


def test_swot_registry_lookup() -> None:
    r = renderer_for("swot")
    assert r.figure_type == "swot"


def test_swot_rejects_missing_fields() -> None:
    r = renderer_for("swot")
    assert not r.validate({}).ok
    assert not r.validate(
        {
            "strengths": {"items": ["a"]},
            "weaknesses": {"items": ["b"]},
            "opportunities": {"items": ["c"]},
        }
    ).ok
    assert not r.validate(
        {
            "strengths": {"items": ["a"]},
            "weaknesses": {"items": ["b"]},
            "opportunities": {"items": ["c"]},
            "threats": {},
        }
    ).ok


def test_swot_renders() -> None:
    r = renderer_for("swot")
    content = {
        "strengths": {"items": ["s1", "s2"]},
        "weaknesses": {"items": ["w1"]},
        "opportunities": {"items": ["o1", "o2", "o3"]},
        "threats": {"items": ["t1"]},
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 4
    assert out.next_shape_id > 1000
    _assert_int_emu(out.shapes_xml)


def test_pyramid_registry_lookup() -> None:
    r = renderer_for("pyramid")
    assert r.figure_type == "pyramid"


def test_pyramid_rejects_missing_fields() -> None:
    r = renderer_for("pyramid")
    assert not r.validate({}).ok
    assert not r.validate({"levels": []}).ok
    assert not r.validate({"levels": [{"label": "a"}, {"label": "b"}]}).ok
    assert not r.validate(
        {"levels": [{"label": "a"}, {"body": "missing"}, {"label": "c"}]}
    ).ok
    assert not r.validate(
        {"levels": [{"label": str(i)} for i in range(6)]}
    ).ok


def test_pyramid_renders() -> None:
    r = renderer_for("pyramid")
    levels = [
        {"label": "Vision"},
        {"label": "Strategy", "body": "中期"},
        {"label": "Tactics"},
        {"label": "Execution", "body": "日次"},
    ]
    content = {"levels": levels}
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= len(levels)
    assert out.next_shape_id > 1000
    _assert_int_emu(out.shapes_xml)
