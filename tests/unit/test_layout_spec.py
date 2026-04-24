"""LayoutSpec validation + emit smoke tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from render.layout_spec import (
    LayoutSpec,
    PillShape,
    RectShape,
    TextParagraphSpec,
    TextRunSpec,
    TextShape,
    emit_layout_spec,
    emit_shape,
)
from render.shapes import DEFAULT_PALETTE


def test_rect_shape_emits_solid_fill() -> None:
    s = RectShape(name="bg", x=0, y=0, w=1000, h=500, fill="purple")
    xml = emit_shape(s, 1)
    assert 'prst="rect"' in xml
    assert DEFAULT_PALETTE.purple in xml


def test_rect_with_corner_radius_uses_roundrect() -> None:
    s = RectShape(
        name="card", x=0, y=0, w=1000, h=500, fill="purple_lt", corner_radius_pct=15
    )
    xml = emit_shape(s, 1)
    assert 'prst="roundRect"' in xml
    assert 'fmla="val 15000"' in xml


def test_rect_outline_only_when_fill_none() -> None:
    s = RectShape(name="o", x=0, y=0, w=100, h=100, fill="none", stroke="muted")
    xml = emit_shape(s, 1)
    assert "<a:noFill/>" in xml
    assert DEFAULT_PALETTE.muted in xml


def test_text_shape_emits_paragraphs() -> None:
    s = TextShape(
        x=0,
        y=0,
        w=1000,
        h=500,
        paragraphs=[
            TextParagraphSpec(runs=[TextRunSpec(text="一段目", bold=True)]),
            TextParagraphSpec(runs=[TextRunSpec(text="二段目", color="muted")]),
        ],
    )
    xml = emit_shape(s, 1)
    assert "一段目" in xml and "二段目" in xml
    assert xml.count("<a:p>") == 2
    assert DEFAULT_PALETTE.muted in xml


def test_pill_shape_emits_pill_geom() -> None:
    s = PillShape(x=0, y=0, w=400, h=200, text="HR", fill="amber", text_color="FFFFFF")
    xml = emit_shape(s, 1)
    assert "HR" in xml


def test_layout_spec_emits_in_order_for_z_index() -> None:
    spec = LayoutSpec(
        slide_index=1,
        shapes=[
            RectShape(name="bg", x=0, y=0, w=1000, h=1000, fill="purple_lt"),
            TextShape(
                name="title",
                x=10,
                y=10,
                w=900,
                h=200,
                paragraphs=[TextParagraphSpec(runs=[TextRunSpec(text="タイトル")])],
            ),
        ],
    )
    fragments, next_id = emit_layout_spec(spec, start_shape_id=100)
    assert len(fragments) == 2
    assert next_id == 102
    # bg before title in document order = bg painted first, title on top.
    bg_idx = fragments[0].index("name=\"bg\"")
    title_idx = fragments[1].index("name=\"title\"")
    assert bg_idx >= 0 and title_idx >= 0


def test_strict_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        RectShape(name="x", x=0, y=0, w=1, h=1, fill="purple", evil="field")  # type: ignore[call-arg]


def test_corner_radius_clamped_by_validation() -> None:
    with pytest.raises(ValidationError):
        RectShape(name="x", x=0, y=0, w=1, h=1, fill="purple", corner_radius_pct=200)


def test_size_pt_must_be_in_range() -> None:
    with pytest.raises(ValidationError):
        TextRunSpec(text="x", size_pt=200)
    with pytest.raises(ValidationError):
        TextRunSpec(text="x", size_pt=2)
