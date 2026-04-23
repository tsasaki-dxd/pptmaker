"""Pyramid (stacked trapezoid-like bands approximated by rectangles)."""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register


@register
class PyramidRenderer(FigureRenderer):
    figure_type = "pyramid"
    description = (
        "Stacked pyramid with 3-5 levels (top = narrowest). "
        "content: {levels: [{label, body?}]}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "levels": [
            {"label": "頂点", "body": "最上位"},
            {"label": "中位", "body": "中位層"},
            {"label": "基盤", "body": "土台"},
        ],
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        levels = content.get("levels")
        if not isinstance(levels, list) or not (3 <= len(levels) <= 5):
            return ValidationResult(False, ("levels must be list of length 3-5",))
        for i, lvl in enumerate(levels):
            if not isinstance(lvl, dict) or not lvl.get("label"):
                return ValidationResult(False, (f"levels[{i}].label required",))
        return ValidationResult(True)

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        levels: list[dict[str, str]] = content["levels"]
        n = len(levels)

        gap = 40000
        band_h = (container.h - gap * (n - 1)) // n
        cx = container.x + container.w // 2
        min_w = container.w // 4
        max_w = container.w
        palette_fills = (p.purple_dk, p.purple, p.purple_lt, p.amber, p.green)

        shapes: list[str] = []
        sid = ctx.next_shape_id

        for i, lvl in enumerate(levels):
            ratio = (i + 1) / n
            band_w = min_w + round((max_w - min_w) * ratio)
            x = cx - band_w // 2
            y = container.y + (band_h + gap) * i
            fill = palette_fills[i % len(palette_fills)]

            shapes.append(rect_shape(sid, f"pyr-band-{i}", x, y, band_w, band_h, fill))
            sid += 1

            body = lvl.get("body", "")
            label_h = band_h if not body else band_h // 2
            shapes.append(
                text_box(
                    sid,
                    f"pyr-label-{i}",
                    x + 120000,
                    y + 80000,
                    band_w - 240000,
                    label_h - 80000,
                    lvl["label"],
                    size_pt=12,
                    bold=True,
                    color="FFFFFF",
                    align="ctr",
                    font=ctx.font,
                )
            )
            sid += 1
            if body and band_h > 360000:
                shapes.append(
                    text_box(
                        sid,
                        f"pyr-body-{i}",
                        x + 120000,
                        y + label_h,
                        band_w - 240000,
                        band_h - label_h - 40000,
                        body,
                        size_pt=9,
                        color="FFFFFF",
                        align="ctr",
                        font=ctx.font,
                    )
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
