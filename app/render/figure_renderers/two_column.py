"""Two-column layout (aim / deliverable / cost boxes etc.)."""

from __future__ import annotations

from typing import Any

from ..shapes import rect_outline, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register


@register
class TwoColumnRenderer(FigureRenderer):
    figure_type = "two_column"
    description = (
        "Left / right columns with optional bottom box. "
        "content: {left: {title, body}, right: {title, body}, footer?: {title, body}}"
    )

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        for side in ("left", "right"):
            if not isinstance(content.get(side), dict):
                return ValidationResult(False, (f"{side} must be object",))
            if "title" not in content[side]:
                return ValidationResult(False, (f"{side}.title missing",))
        return ValidationResult(True)

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        has_footer = bool(content.get("footer"))
        gap = 200000
        col_w = (container.w - gap) // 2
        main_h = container.h - (700000 if has_footer else 0)

        shapes: list[str] = []
        sid = ctx.next_shape_id

        for i, key in enumerate(("left", "right")):
            col = content[key]
            x = container.x + (col_w + gap) * i
            y = container.y
            shapes.append(rect_shape(sid, f"col-bg-{key}", x, y, col_w, main_h, p.purple_bg))
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"col-title-{key}",
                    x + 180000,
                    y + 160000,
                    col_w - 360000,
                    420000,
                    col["title"],
                    size_pt=13,
                    bold=True,
                    color=p.purple_dk,
                    font=ctx.font,
                )
            )
            sid += 1
            if "body" in col:
                shapes.append(
                    text_box(
                        sid,
                        f"col-body-{key}",
                        x + 180000,
                        y + 640000,
                        col_w - 360000,
                        main_h - 820000,
                        col["body"],
                        size_pt=11,
                        color=p.black,
                        font=ctx.font,
                    )
                )
                sid += 1

        if has_footer:
            f = content["footer"]
            fy = container.y + main_h + 100000
            fh = 600000
            shapes.append(
                rect_outline(sid, "footer-box", container.x, fy, container.w, fh, p.purple)
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    "footer-title",
                    container.x + 200000,
                    fy + 120000,
                    container.w - 400000,
                    fh - 240000,
                    f"{f.get('title', '')}  {f.get('body', '')}",
                    size_pt=11,
                    bold=True,
                    color=p.purple_dk,
                    font=ctx.font,
                )
            )
            sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
