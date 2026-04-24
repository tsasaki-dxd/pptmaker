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
    pill_label,
    rect_outline,
    rect_shape,
    resolve_palette_color,
    round_rect_shape,
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


Shape = Annotated[
    RectShape | TextShape | PillShape | LineShape,
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
