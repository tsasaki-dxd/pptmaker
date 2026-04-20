"""Validate / render smoke tests for every registered figure renderer."""

from __future__ import annotations

from render.figure_renderers import list_capabilities, renderer_for
from render.figure_renderers.base import EMUBox, RenderContext
from render.shapes import DEFAULT_FONT, DEFAULT_PALETTE


def _ctx() -> RenderContext:
    return RenderContext(palette=DEFAULT_PALETTE, font=DEFAULT_FONT, next_shape_id=1000)


def _box() -> EMUBox:
    return EMUBox(x=457200, y=1463040, w=11246400, h=4937760)


def test_all_renderers_registered() -> None:
    caps = list_capabilities()
    ftypes = {c["figure_type"] for c in caps}
    for expected in (
        "table",
        "cards_grid",
        "two_column",
        "timeline",
        "stat_callout",
        "bullet_list",
        "comparison",
    ):
        assert expected in ftypes


def test_table_validates_and_renders() -> None:
    r = renderer_for("table")
    content = {
        "headers": ["A", "B", "C"],
        "rows": [["a1", "b1", "c1"], ["a2", "b2", "c2"]],
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert out.shapes_xml
    assert out.next_shape_id > 1000


def test_table_rejects_bad_input() -> None:
    r = renderer_for("table")
    assert not r.validate({"headers": []}).ok
    assert not r.validate({"headers": ["A", "B"], "rows": []}).ok


def test_cards_grid_renders() -> None:
    r = renderer_for("cards_grid")
    out = r.render(
        {"cards": [{"title": "t1", "body": "b1"}, {"title": "t2"}], "columns": 2},
        _box(),
        _ctx(),
    )
    assert out.shapes_xml


def test_two_column_with_footer() -> None:
    r = renderer_for("two_column")
    out = r.render(
        {
            "left": {"title": "ねらい", "body": "本文"},
            "right": {"title": "成果物", "body": "本文"},
            "footer": {"title": "費用", "body": "¥X"},
        },
        _box(),
        _ctx(),
    )
    assert out.shapes_xml


def test_timeline_renders() -> None:
    r = renderer_for("timeline")
    steps = [{"label": f"S{i}", "body": "desc"} for i in range(4)]
    out = r.render({"steps": steps}, _box(), _ctx())
    assert out.shapes_xml


def test_stat_callout_requires_value() -> None:
    r = renderer_for("stat_callout")
    assert not r.validate({"label": "x"}).ok
    assert r.validate({"value": "100M", "label": "売上"}).ok


def test_bullet_list_renders_mixed_items() -> None:
    r = renderer_for("bullet_list")
    out = r.render(
        {"items": ["a", {"text": "b", "sub": "(detail)"}, "c"]},
        _box(),
        _ctx(),
    )
    assert out.shapes_xml


def test_comparison_renders() -> None:
    r = renderer_for("comparison")
    out = r.render(
        {
            "left": {"title": "現状", "items": ["x", "y"]},
            "right": {"title": "理想", "items": ["X", "Y"]},
        },
        _box(),
        _ctx(),
    )
    assert out.shapes_xml
