"""LayoutSpec — the JSON contract between the layout-designer LLM and
the deterministic shape emitter.

The designer's job is to look at a blueprint slide + the template's
fixed metadata and emit a LayoutSpec describing exactly which shapes
to draw, where, and how. This module defines the Pydantic schema for
that handoff plus an emitter that turns a LayoutSpec into the shape
XML fragments the render handler injects into the slide.

Design choices:
  * Pure primitives mode — no figure_type abstraction. The designer
    composes everything from rect / round_rect / text / line / pill.
    This is intentional: the figure_renderer presets gave generic
    output that nobody wanted to ship; we get goal-quality only by
    letting the LLM compose custom layouts content-aware.
  * Coordinates are EMU. The designer is told the body container
    rect so it can stay inside it.
  * Colors accept either 6-char HEX or palette tokens ("purple",
    "muted", "amber", …). Resolution happens at emit time against
    whatever palette is active for the deck (theme-inherited or
    DEFAULT_PALETTE).
  * The schema is strict (extra="forbid") so the LLM can't sneak in
    fields the renderer would silently drop.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .shapes import (
    DEFAULT_FONT,
    DEFAULT_PALETTE,
    Palette,
    TextParagraph,
    TextRun,
    bar_chart_shape,
    line_chart_shape,
    pie_chart_shape,
    pill_label,
    rect_outline,
    rect_shape,
    resolve_palette_color,
    round_rect_shape,
    table_shape,
    text_box_paragraphs,
)

# ---------- shape primitives ----------


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RectShape(_Base):
    kind: Literal["rect"] = "rect"
    name: str = "rect"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    fill: str = "purple"
    stroke: str | None = None
    stroke_width_emu: int = 0
    corner_radius_pct: int = Field(default=0, ge=0, le=50)


class TextRunSpec(_Base):
    text: str
    size_pt: int = Field(default=11, ge=4, le=72)
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str = "black"


class TextParagraphSpec(_Base):
    runs: list[TextRunSpec] = Field(default_factory=list)
    align: Literal["l", "ctr", "r", "just"] = "l"
    indent_level: int = Field(default=0, ge=0, le=8)
    bullet: str | None = None
    line_spacing_pct: int = Field(default=100, ge=50, le=300)
    space_before_pt: int = 0
    space_after_pt: int = 0


class TextShape(_Base):
    kind: Literal["text"] = "text"
    name: str = "text"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    paragraphs: list[TextParagraphSpec] = Field(default_factory=list)
    font: str | None = None
    anchor: Literal["t", "ctr", "b"] = "t"
    auto_fit: bool = True


class PillShape(_Base):
    kind: Literal["pill"] = "pill"
    name: str = "pill"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    text: str
    fill: str = "purple"
    text_color: str = "FFFFFF"
    size_pt: int = Field(default=9, ge=4, le=24)
    font: str | None = None


class LineShape(_Base):
    """Thin filled rectangle used as a horizontal or vertical rule.

    OOXML's `<p:cxnSp>` connector would be the "right" element but
    rectangles render identically and avoid a second emit code path.
    """

    kind: Literal["line"] = "line"
    name: str = "line"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    color: str = "border"


# ---- Table / Chart specs -----------------------------------------------
#
# These are composite primitives — the LLM emits structured data
# (rows, bars, slices) and the deterministic emitter expands it into
# multiple OOXML shapes. The LLM never has to compute bar widths or
# pie angles itself.


class CellSpec(_Base):
    """Per-cell override. Any field set to None inherits the row /
    header default. ``col_span`` / ``row_span`` cover adjacent cells —
    the renderer emits OOXML ``gridSpan``/``rowSpan`` plus
    ``hMerge``/``vMerge`` continuation cells; the cells the span
    covers should still appear in ``rows`` (their content is dropped).
    """

    text: str = ""
    bold: bool | None = None
    align: Literal["l", "ctr", "r"] | None = None
    fill: str | None = None
    text_color: str | None = None
    col_span: int = Field(default=1, ge=1)
    row_span: int = Field(default=1, ge=1)


class ColumnSpec(_Base):
    """Per-column override. ``weight`` controls relative width
    (defaults to 1 — equal split); ``align`` is the default text
    alignment for body cells in this column (header keeps its own
    style)."""

    weight: float = Field(default=1.0, gt=0)
    align: Literal["l", "ctr", "r"] = "l"


class TableShape(_Base):
    """Tabular data.

    ``rows`` may contain plain strings (simple cells) or ``CellSpec``
    dicts for richer per-cell styling and spans. ``rows[0]`` is the
    header row when ``header`` is true.

    Column behavior is controlled by ``columns`` (preferred) or the
    legacy ``column_weights`` shorthand. If both are supplied,
    ``columns`` wins. If neither is supplied, columns are equal-width
    and left-aligned.
    """

    kind: Literal["table"] = "table"
    name: str = "table"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    rows: list[list[str | CellSpec]] = Field(min_length=1)
    columns: list[ColumnSpec] | None = None
    column_weights: list[float] | None = None
    header: bool = True
    alt_row_bg: bool = False
    header_fill: str = "primary"
    header_text_color: str = "white"
    body_text_color: str = "text_dark"
    alt_row_fill: str = "primary_bg"
    border_color: str = "border"
    font_size_pt: int = Field(default=10, ge=6, le=24)


class BarItem(_Base):
    label: str
    value: float
    color: str | None = None


class BarSeries(_Base):
    """One series of a multi-series bar chart. ``values`` must align
    with the chart's ``categories`` 1:1."""

    name: str = ""
    values: list[float] = Field(min_length=1)
    color: str | None = None


class BarChartShape(_Base):
    """Vertical or horizontal bar chart.

    Two input modes:

    1. Single-series (shorthand): pass ``items`` only. Each item
       becomes one bar; per-item ``color`` overrides ``bar_color``.

    2. Multi-series: pass ``series`` + ``categories``. Each series'
       ``values`` must match ``len(categories)``. ``mode`` selects
       layout: ``"grouped"`` (clustered side-by-side), ``"stacked"``
       (cumulative segments), or ``"stacked100"`` (each category
       normalized to 100%).

    ``items`` and ``series`` are mutually exclusive.
    """

    kind: Literal["bar_chart"] = "bar_chart"
    name: str = "bar_chart"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    items: list[BarItem] | None = None
    series: list[BarSeries] | None = None
    categories: list[str] | None = None
    mode: Literal["grouped", "stacked", "stacked100"] = "grouped"
    orientation: Literal["v", "h"] = "v"
    show_values: bool = True
    value_format: str = "{:g}"
    bar_color: str = "primary"
    axis_color: str = "border"
    label_color: str = "muted"
    value_color: str = "text_dark"
    font_size_pt: int = Field(default=10, ge=6, le=24)

    def model_post_init(self, __context: object) -> None:  # type: ignore[override]
        if self.items is None and self.series is None:
            raise ValueError("bar_chart requires either `items` or `series`")
        if self.items is not None and self.series is not None:
            raise ValueError("bar_chart accepts `items` OR `series`, not both")
        if self.series is not None:
            if not self.categories:
                raise ValueError("multi-series bar_chart requires `categories`")
            n_cats = len(self.categories)
            for s in self.series:
                if len(s.values) != n_cats:
                    raise ValueError(
                        f"series '{s.name}' has {len(s.values)} values "
                        f"but categories has {n_cats}"
                    )


class LineSeries(_Base):
    name: str = ""
    values: list[float] = Field(min_length=2)
    color: str | None = None


class LineChartShape(_Base):
    """Multi-series line chart sharing one x axis."""

    kind: Literal["line_chart"] = "line_chart"
    name: str = "line_chart"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    series: list[LineSeries] = Field(min_length=1)
    x_labels: list[str] | None = None
    show_markers: bool = True
    axis_color: str = "border"
    label_color: str = "muted"
    line_width_emu: int = Field(default=19050, ge=1)
    marker_radius_emu: int = Field(default=38100, ge=1)
    font_size_pt: int = Field(default=9, ge=6, le=24)


class PieSlice(_Base):
    label: str = ""
    value: float = Field(gt=0)
    color: str | None = None


class PieChartShape(_Base):
    """Pie chart using OOXML pie preset geometry. Labels are *not*
    drawn inside the pie; place TextShapes / PillShapes around it
    if labelling is needed.
    """

    kind: Literal["pie_chart"] = "pie_chart"
    name: str = "pie_chart"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    slices: list[PieSlice] = Field(min_length=1)


Shape = Annotated[
    (
        RectShape | TextShape | PillShape | LineShape
        | TableShape | BarChartShape | LineChartShape | PieChartShape
    ),
    Field(discriminator="kind"),
]


# ---------- whole-slide spec ----------


class LayoutSpec(_Base):
    """Per-slide layout. ``shapes`` are emitted in document order, so
    the LLM controls Z-order by the position it puts each shape in
    the list (earlier = behind, later = in front).
    """

    slide_index: int = Field(ge=1)
    shapes: list[Shape] = Field(default_factory=list)


# ---------- emitter ----------


def _to_paragraph(p: TextParagraphSpec, palette: Palette) -> TextParagraph:
    return TextParagraph(
        runs=tuple(
            TextRun(
                text=r.text,
                size_pt=r.size_pt,
                bold=r.bold,
                italic=r.italic,
                underline=r.underline,
                color=resolve_palette_color(r.color, palette),
            )
            for r in p.runs
        ),
        align=p.align,
        indent_level=p.indent_level,
        bullet=p.bullet,
        line_spacing_pct=p.line_spacing_pct,
        space_before_pt=p.space_before_pt,
        space_after_pt=p.space_after_pt,
    )


def emit_shape(
    shape: Shape,
    sp_id: int,
    *,
    palette: Palette = DEFAULT_PALETTE,
    font: str = DEFAULT_FONT,
) -> str:
    """Translate one LayoutSpec shape into PPTX shape XML."""
    if isinstance(shape, RectShape):
        fill = resolve_palette_color(shape.fill, palette)
        stroke = (
            resolve_palette_color(shape.stroke, palette) if shape.stroke else None
        )
        if shape.corner_radius_pct > 0:
            return round_rect_shape(
                sp_id,
                shape.name,
                shape.x,
                shape.y,
                shape.w,
                shape.h,
                fill,
                corner_radius_pct=shape.corner_radius_pct,
                line_color=stroke,
                line_width_emu=shape.stroke_width_emu,
            )
        # Stroke-only "outline" shape when fill is "none".
        if shape.fill.lower() in {"none", "transparent"} and stroke is not None:
            return rect_outline(
                sp_id,
                shape.name,
                shape.x,
                shape.y,
                shape.w,
                shape.h,
                stroke,
                line_width_emu=shape.stroke_width_emu or 9525,
            )
        return rect_shape(
            sp_id,
            shape.name,
            shape.x,
            shape.y,
            shape.w,
            shape.h,
            fill,
            line_color=stroke,
            line_width_emu=shape.stroke_width_emu,
        )

    if isinstance(shape, TextShape):
        paragraphs = [_to_paragraph(p, palette) for p in shape.paragraphs]
        return text_box_paragraphs(
            sp_id,
            shape.name,
            shape.x,
            shape.y,
            shape.w,
            shape.h,
            paragraphs,
            font=shape.font or font,
            anchor=shape.anchor,
            auto_fit=shape.auto_fit,
        )

    if isinstance(shape, PillShape):
        return pill_label(
            sp_id,
            shape.name,
            shape.x,
            shape.y,
            shape.w,
            shape.h,
            shape.text,
            resolve_palette_color(shape.fill, palette),
            text_color=resolve_palette_color(shape.text_color, palette),
            size_pt=shape.size_pt,
            font=shape.font or font,
        )

    if isinstance(shape, LineShape):
        return rect_shape(
            sp_id,
            shape.name,
            shape.x,
            shape.y,
            shape.w,
            shape.h,
            resolve_palette_color(shape.color, palette),
        )

    if isinstance(shape, TableShape):
        # Translate CellSpec / ColumnSpec into a renderer-friendly
        # form. Plain string cells become a CellSpec stub here so the
        # emitter has a single shape to work with.
        rows_for_emit: list[list[dict[str, object]]] = []
        for row in shape.rows:
            row_out: list[dict[str, object]] = []
            for cell in row:
                if isinstance(cell, CellSpec):
                    row_out.append(
                        {
                            "text": cell.text,
                            "bold": cell.bold,
                            "align": cell.align,
                            "fill": (
                                resolve_palette_color(cell.fill, palette)
                                if cell.fill
                                else None
                            ),
                            "text_color": (
                                resolve_palette_color(cell.text_color, palette)
                                if cell.text_color
                                else None
                            ),
                            "col_span": cell.col_span,
                            "row_span": cell.row_span,
                        }
                    )
                else:
                    row_out.append(
                        {
                            "text": cell,
                            "bold": None,
                            "align": None,
                            "fill": None,
                            "text_color": None,
                            "col_span": 1,
                            "row_span": 1,
                        }
                    )
            rows_for_emit.append(row_out)

        if shape.columns:
            columns_for_emit = [
                {"weight": c.weight, "align": c.align} for c in shape.columns
            ]
        elif shape.column_weights:
            columns_for_emit = [
                {"weight": w, "align": "l"} for w in shape.column_weights
            ]
        else:
            columns_for_emit = None

        return table_shape(
            sp_id,
            shape.name,
            shape.x,
            shape.y,
            shape.w,
            shape.h,
            rows=rows_for_emit,
            columns=columns_for_emit,
            header=shape.header,
            alt_row_bg=shape.alt_row_bg,
            header_fill=resolve_palette_color(shape.header_fill, palette),
            header_text_color=resolve_palette_color(shape.header_text_color, palette),
            body_text_color=resolve_palette_color(shape.body_text_color, palette),
            alt_row_fill=resolve_palette_color(shape.alt_row_fill, palette),
            border_color=resolve_palette_color(shape.border_color, palette),
            font_size_pt=shape.font_size_pt,
            font=font,
        )

    if isinstance(shape, BarChartShape):
        if shape.items is not None:
            items_for_emit = [
                (
                    item.label,
                    item.value,
                    resolve_palette_color(item.color, palette) if item.color else None,
                )
                for item in shape.items
            ]
            series_for_emit = None
            categories_for_emit = None
        else:
            assert shape.series is not None and shape.categories is not None
            items_for_emit = None
            series_for_emit = [
                (
                    s.name,
                    list(s.values),
                    resolve_palette_color(s.color, palette) if s.color else None,
                )
                for s in shape.series
            ]
            categories_for_emit = list(shape.categories)
        return bar_chart_shape(
            sp_id,
            shape.name,
            shape.x,
            shape.y,
            shape.w,
            shape.h,
            items=items_for_emit,
            series=series_for_emit,
            categories=categories_for_emit,
            mode=shape.mode,
            orientation=shape.orientation,
            show_values=shape.show_values,
            value_format=shape.value_format,
            bar_color=resolve_palette_color(shape.bar_color, palette),
            axis_color=resolve_palette_color(shape.axis_color, palette),
            label_color=resolve_palette_color(shape.label_color, palette),
            value_color=resolve_palette_color(shape.value_color, palette),
            font_size_pt=shape.font_size_pt,
            font=font,
        )

    if isinstance(shape, LineChartShape):
        return line_chart_shape(
            sp_id,
            shape.name,
            shape.x,
            shape.y,
            shape.w,
            shape.h,
            series=[
                (
                    s.name,
                    list(s.values),
                    resolve_palette_color(s.color, palette) if s.color else None,
                )
                for s in shape.series
            ],
            x_labels=list(shape.x_labels) if shape.x_labels else None,
            show_markers=shape.show_markers,
            axis_color=resolve_palette_color(shape.axis_color, palette),
            label_color=resolve_palette_color(shape.label_color, palette),
            line_width_emu=shape.line_width_emu,
            marker_radius_emu=shape.marker_radius_emu,
            font_size_pt=shape.font_size_pt,
            font=font,
        )

    if isinstance(shape, PieChartShape):
        return pie_chart_shape(
            sp_id,
            shape.name,
            shape.x,
            shape.y,
            shape.w,
            shape.h,
            slices=[
                (
                    sl.label,
                    sl.value,
                    resolve_palette_color(sl.color, palette) if sl.color else None,
                )
                for sl in shape.slices
            ],
            palette=palette,
        )

    raise ValueError(f"unknown shape kind: {shape!r}")


def emit_layout_spec(
    spec: LayoutSpec,
    *,
    palette: Palette = DEFAULT_PALETTE,
    font: str = DEFAULT_FONT,
    start_shape_id: int = 1000,
) -> tuple[list[str], int]:
    """Emit every shape in `spec.shapes` and return ``(xml_fragments,
    next_shape_id)`` so the caller can chain with other shape sources
    that share the same id-space."""
    fragments: list[str] = []
    sid = start_shape_id
    for shape in spec.shapes:
        fragments.append(emit_shape(shape, sid, palette=palette, font=font))
        sid += 1
    return fragments, sid
