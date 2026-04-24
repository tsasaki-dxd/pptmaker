"""Left-right comparison with checklist items."""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import fit_stack, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register


@register
class ComparisonRenderer(FigureRenderer):
    figure_type = "comparison"
    description = (
        "Side-by-side comparison (before/after, current/ideal). "
        "content: {left: {title, items: [str]}, right: {title, items: [str]}}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "left": {"title": "現状", "items": ["課題1", "課題2"]},
        "right": {"title": "理想", "items": ["改善1", "改善2"]},
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        for side in ("left", "right"):
            block = content.get(side)
            if not isinstance(block, dict):
                return ValidationResult(False, (f"{side} must be object",))
            if not isinstance(block.get("items"), list):
                return ValidationResult(False, (f"{side}.items must be list",))
        return ValidationResult(True)

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        gap = 200000
        col_w = (container.w - gap) // 2

        shapes: list[str] = []
        sid = ctx.next_shape_id

        for i, (key, accent) in enumerate((("left", p.muted), ("right", p.purple))):
            col = content[key]
            x = container.x + (col_w + gap) * i
            shapes.append(rect_shape(sid, f"cmp-bg-{key}", x, container.y, col_w, container.h, p.bg_alt))
            sid += 1
            shapes.append(rect_shape(sid, f"cmp-bar-{key}", x, container.y, 60000, container.h, accent))
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"cmp-title-{key}",
                    x + 200000,
                    container.y + 140000,
                    col_w - 400000,
                    420000,
                    col.get("title", ""),
                    size_pt=13,
                    bold=True,
                    color=accent,
                    font=ctx.font,
                )
            )
            sid += 1

            items: list[str] = col["items"]
            # Reserve 640k for title + top padding, 60k for bottom margin.
            # fit_stack collapses gap then shrinks per-item height to fit.
            item_h, item_gap = fit_stack(
                container_h=container.h,
                n=len(items),
                natural_h=380000,
                min_h=160000,
                gap=20000,
                min_gap=0,
                header_h=640000,
                footer_h=60000,
            )
            for j, item in enumerate(items):
                shapes.append(
                    text_box(
                        sid,
                        f"cmp-item-{key}-{j}",
                        x + 260000,
                        container.y + 640000 + (item_h + item_gap) * j,
                        col_w - 440000,
                        item_h,
                        f"・ {item}",
                        size_pt=10,
                        color=p.black,
                        font=ctx.font,
                        auto_fit=True,
                    )
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
