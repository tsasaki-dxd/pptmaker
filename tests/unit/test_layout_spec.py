"""LayoutSpec validation + emit smoke tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from render.layout_spec import (
    BarChartShape,
    BarItem,
    BarSeries,
    CellSpec,
    ColumnSpec,
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
    # Both bars still emit (one per category); the negative one
    # renders at min height.
    assert xml.count('name="bar_chart_c0_s0"') == 1
    assert xml.count('name="bar_chart_c1_s0"') == 1


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


# ---- Table cell / column / span ---------------------------------------


def test_table_cell_spec_overrides_styling() -> None:
    s = TableShape(
        x=0, y=0, w=4_000_000, h=2_000_000,
        rows=[
            ["項目", "数値"],
            ["A", CellSpec(text="999", bold=True, align="r", text_color="amber")],
        ],
    )
    xml = emit_shape(s, 1)
    # Header cell: bold body, default header fill.
    assert "999" in xml
    # The amber color shows up on the overridden cell.
    assert DEFAULT_PALETTE.amber in xml
    # Right alignment came through.
    assert 'algn="r"' in xml


def test_table_cell_fill_override_paints_alternate_background() -> None:
    s = TableShape(
        x=0, y=0, w=2_000_000, h=1_000_000,
        rows=[
            ["h1", "h2"],
            [CellSpec(text="hot", fill="amber"), "ok"],
        ],
        header=True,
        alt_row_bg=False,
    )
    xml = emit_shape(s, 1)
    assert DEFAULT_PALETTE.amber in xml


def test_table_columns_take_precedence_over_column_weights() -> None:
    s = TableShape(
        x=0, y=0, w=600_000, h=300_000,
        rows=[["a", "b", "c"]],
        columns=[
            ColumnSpec(weight=1, align="l"),
            ColumnSpec(weight=4, align="ctr"),
            ColumnSpec(weight=1, align="r"),
        ],
        column_weights=[1, 1, 1],  # should be ignored
        header=False,
    )
    xml = emit_shape(s, 1)
    import re

    widths = [int(m) for m in re.findall(r'<a:gridCol w="(\d+)"', xml)]
    # Middle column ~4x outer ones (allow 1 EMU rounding drift).
    assert widths[1] >= widths[0] * 3
    assert sum(widths) == 600_000
    # The 'r' alignment from the third column shows up in body cells.
    assert 'algn="r"' in xml


def test_table_col_span_emits_grid_span_and_hmerge() -> None:
    s = TableShape(
        x=0, y=0, w=900_000, h=300_000,
        rows=[
            [CellSpec(text="merged header", col_span=3), "", ""],
            ["a", "b", "c"],
        ],
        header=True,
    )
    xml = emit_shape(s, 1)
    assert 'gridSpan="3"' in xml
    # Two continuation cells covered by the span.
    assert xml.count('hMerge="1"') == 2


def test_table_row_span_emits_row_span_and_vmerge() -> None:
    s = TableShape(
        x=0, y=0, w=600_000, h=900_000,
        rows=[
            [CellSpec(text="L", row_span=2), "header2"],
            ["", "row2-b"],
            ["row3-a", "row3-b"],
        ],
        header=False,
    )
    xml = emit_shape(s, 1)
    assert 'rowSpan="2"' in xml
    assert xml.count('vMerge="1"') == 1


def test_table_span_clamped_when_oversized() -> None:
    # row_span/col_span beyond grid bounds should not crash.
    s = TableShape(
        x=0, y=0, w=400_000, h=200_000,
        rows=[[CellSpec(text="huge", col_span=99, row_span=99)]],
        header=False,
    )
    xml = emit_shape(s, 1)
    # Single cell, no merge attrs needed.
    assert "<a:tbl>" in xml


# ---- Bar chart multi-series + modes -----------------------------------


def test_bar_chart_multi_series_grouped_emits_one_bar_per_series_per_category() -> None:
    s = BarChartShape(
        x=0, y=0, w=4_000_000, h=2_000_000,
        series=[
            BarSeries(name="2024", values=[10, 20, 30]),
            BarSeries(name="2025", values=[15, 25, 5]),
        ],
        categories=["Q1", "Q2", "Q3"],
        mode="grouped",
    )
    xml = emit_shape(s, 50)
    # 3 categories * 2 series = 6 bars, plus 1 axis = 7 sp; values + cat
    # labels on top.
    assert xml.count('name="bar_chart_c0_s0"') == 1
    assert xml.count('name="bar_chart_c2_s1"') == 1
    # Different default series colors used.
    assert DEFAULT_PALETTE.purple in xml
    assert DEFAULT_PALETTE.amber in xml


def test_bar_chart_stacked_segments_share_x_position() -> None:
    s = BarChartShape(
        x=0, y=0, w=2_000_000, h=2_000_000,
        series=[
            BarSeries(name="A", values=[10, 20]),
            BarSeries(name="B", values=[30, 10]),
        ],
        categories=["Q1", "Q2"],
        mode="stacked",
        show_values=False,
    )
    xml = emit_shape(s, 50)
    # 2 cats * 2 series = 4 segments + 1 axis + 2 cat labels = 7 sp.
    assert xml.count('name="bar_chart_c') == 4 + 0  # only segments named c%d_s%d
    assert xml.count('name="bar_chart_c0_s') == 2
    assert xml.count('name="bar_chart_c1_s') == 2


def test_bar_chart_stacked100_normalizes_to_full_height() -> None:
    s = BarChartShape(
        x=0, y=0, w=2_000_000, h=2_000_000,
        series=[
            BarSeries(name="A", values=[1, 2]),
            BarSeries(name="B", values=[3, 8]),  # cat 0 sum = 4, cat 1 sum = 10
        ],
        categories=["Q1", "Q2"],
        mode="stacked100",
        show_values=False,
    )
    xml = emit_shape(s, 50)
    # Should still produce 4 segments. Heights normalized so each
    # category sums to the same total height (within rounding).
    assert xml.count('name="bar_chart_c0_s') == 2
    assert xml.count('name="bar_chart_c1_s') == 2


def test_bar_chart_rejects_items_and_series_together() -> None:
    with pytest.raises(ValidationError):
        BarChartShape(
            x=0, y=0, w=100, h=100,
            items=[BarItem(label="A", value=1)],
            series=[BarSeries(name="x", values=[1])],
            categories=["A"],
        )


def test_bar_chart_requires_categories_when_series_used() -> None:
    with pytest.raises(ValidationError):
        BarChartShape(
            x=0, y=0, w=100, h=100,
            series=[BarSeries(name="x", values=[1, 2])],
        )


def test_bar_chart_series_values_must_match_categories_length() -> None:
    with pytest.raises(ValidationError):
        BarChartShape(
            x=0, y=0, w=100, h=100,
            series=[BarSeries(name="x", values=[1, 2, 3])],
            categories=["A", "B"],
        )


def test_bar_chart_requires_at_least_one_input() -> None:
    with pytest.raises(ValidationError):
        BarChartShape(x=0, y=0, w=100, h=100)


def test_bar_chart_horizontal_stacked_works() -> None:
    s = BarChartShape(
        x=0, y=0, w=4_000_000, h=2_000_000,
        series=[
            BarSeries(name="A", values=[5, 10]),
            BarSeries(name="B", values=[3, 7]),
        ],
        categories=["Q1", "Q2"],
        mode="stacked",
        orientation="h",
        show_values=False,
    )
    xml = emit_shape(s, 50)
    assert xml.count('name="bar_chart_c0_s') == 2
    assert xml.count('name="bar_chart_c1_s') == 2
