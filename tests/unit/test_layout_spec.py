"""LayoutSpec validation + emit smoke tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from render.layout_spec import (
    BarChartShape,
    BarItem,
    LayoutSpec,
    LineChartShape,
    LineSeries,
    PieChartShape,
    PieSlice,
    PillShape,
    RectShape,
    TableShape,
    TextParagraphSpec,
    TextRunSpec,
    TextShape,
    emit_layout_spec,
    emit_shape,
)
from render.shapes import DEFAULT_PALETTE, resolve_palette_color


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


# ---- Palette aliases ---------------------------------------------------


def test_palette_alias_primary_resolves_to_purple() -> None:
    assert resolve_palette_color("primary") == DEFAULT_PALETTE.purple
    assert resolve_palette_color("primary_dark") == DEFAULT_PALETTE.purple_dk
    assert resolve_palette_color("primary_lt") == DEFAULT_PALETTE.purple_lt
    assert resolve_palette_color("primary_bg") == DEFAULT_PALETTE.purple_bg


def test_palette_alias_text_dark_resolves_to_black() -> None:
    assert resolve_palette_color("text_dark") == DEFAULT_PALETTE.black


def test_palette_alias_white_is_fixed_hex() -> None:
    # `white` previously fell through to purple — verify it now sticks.
    assert resolve_palette_color("white") == "FFFFFF"


def test_palette_unknown_token_still_falls_back_to_purple() -> None:
    # Unknown alias should NOT raise; matches old behaviour.
    assert resolve_palette_color("nonsense") == DEFAULT_PALETTE.purple


# ---- Table -------------------------------------------------------------


def test_table_shape_emits_graphic_frame_with_rows() -> None:
    s = TableShape(
        x=0,
        y=0,
        w=4_000_000,
        h=2_000_000,
        rows=[
            ["項目", "数値"],
            ["A", "10"],
            ["B", "20"],
        ],
        header=True,
    )
    xml = emit_shape(s, 1)
    assert "<p:graphicFrame>" in xml
    assert "<a:tbl>" in xml
    assert xml.count("<a:tr") == 3
    assert xml.count("<a:tc>") == 6
    assert "項目" in xml and "20" in xml
    assert 'firstRow="1"' in xml


def test_table_column_weights_sum_to_total_width() -> None:
    s = TableShape(
        x=0,
        y=0,
        w=1_000_000,
        h=500_000,
        rows=[["a", "b", "c"]],
        column_weights=[1.0, 2.0, 1.0],
        header=False,
    )
    xml = emit_shape(s, 1)
    import re

    widths = [int(m) for m in re.findall(r'<a:gridCol w="(\d+)"', xml)]
    assert sum(widths) == 1_000_000
    # 2x weight column should be the largest.
    assert widths[1] > widths[0] and widths[1] > widths[2]


def test_table_requires_at_least_one_row() -> None:
    with pytest.raises(ValidationError):
        TableShape(x=0, y=0, w=100, h=100, rows=[])


# ---- Bar chart ---------------------------------------------------------


def test_bar_chart_emits_one_bar_per_item_plus_axis() -> None:
    s = BarChartShape(
        x=0,
        y=0,
        w=2_000_000,
        h=1_000_000,
        items=[
            BarItem(label="Q1", value=10),
            BarItem(label="Q2", value=20),
            BarItem(label="Q3", value=15),
        ],
    )
    xml = emit_shape(s, 50)
    # 1 axis + 3 bars + 3 value labels + 3 category labels = 10 sp.
    assert xml.count("<p:sp>") == 10
    assert "Q1" in xml and "Q3" in xml


def test_bar_chart_horizontal_uses_left_axis() -> None:
    s = BarChartShape(
        x=0,
        y=0,
        w=2_000_000,
        h=1_000_000,
        orientation="h",
        items=[BarItem(label="A", value=5), BarItem(label="B", value=10)],
        show_values=False,
    )
    xml = emit_shape(s, 50)
    # 1 axis + 2 bars + 2 labels = 5 sp (no value labels).
    assert xml.count("<p:sp>") == 5


def test_bar_chart_negative_value_clamped_not_rejected() -> None:
    s = BarChartShape(
        x=0,
        y=0,
        w=1_000_000,
        h=500_000,
        items=[BarItem(label="A", value=-5), BarItem(label="B", value=10)],
    )
    xml = emit_shape(s, 50)
    # Both bars still emit; the negative one renders at min height.
    assert xml.count("name=\"bar_chart_bar") == 2


# ---- Line chart --------------------------------------------------------


def test_line_chart_emits_segments_and_markers() -> None:
    s = LineChartShape(
        x=0,
        y=0,
        w=4_000_000,
        h=2_000_000,
        series=[LineSeries(name="売上", values=[10, 20, 15, 30])],
        x_labels=["Q1", "Q2", "Q3", "Q4"],
    )
    xml = emit_shape(s, 100)
    # 4 points → 3 segments
    assert xml.count("<p:cxnSp>") == 3
    # 4 markers
    assert xml.count('prst="ellipse"') == 4
    # 4 axis labels
    assert "Q4" in xml


def test_line_chart_requires_at_least_two_points_per_series() -> None:
    with pytest.raises(ValidationError):
        LineSeries(name="s", values=[5])


# ---- Pie chart ---------------------------------------------------------


def test_pie_chart_emits_one_sp_per_positive_slice() -> None:
    s = PieChartShape(
        x=0,
        y=0,
        w=2_000_000,
        h=2_000_000,
        slices=[
            PieSlice(label="A", value=50),
            PieSlice(label="B", value=30),
            PieSlice(label="C", value=20),
        ],
    )
    xml = emit_shape(s, 200)
    assert xml.count('prst="pie"') == 3
    # Angle adj values are present.
    assert "adj1" in xml and "adj2" in xml


def test_pie_chart_rejects_non_positive_slice_value() -> None:
    with pytest.raises(ValidationError):
        PieSlice(label="A", value=0)
    with pytest.raises(ValidationError):
        PieSlice(label="A", value=-1)
