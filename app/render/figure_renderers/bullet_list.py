"""Structured bullet list."""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import fit_stack, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register


@register
class BulletListRenderer(FigureRenderer):
    figure_type = "bullet_list"
    description = "Vertical bullet list. content: {items: [str | {text, sub?}]}"
    input_schema_example: ClassVar[dict[str, Any]] = {
        "items": ["要点1", "要点2", {"text": "要点3", "sub": "補足"}],
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        items = content.get("items")
        if not isinstance(items, list) or not items:
            return ValidationResult(False, ("items must be non-empty list",))
        return ValidationResult(True)

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        items = content["items"]
        item_h, gap = fit_stack(
            container_h=container.h,
            n=len(items),
            natural_h=520000,
            min_h=180000,
            gap=100000,
            min_gap=20000,
        )

        shapes: list[str] = []
        sid = ctx.next_shape_id

        for i, item in enumerate(items):
            text = item if isinstance(item, str) else item.get("text", "")
            y = container.y + (item_h + gap) * i
            has_sub = isinstance(item, dict) and item.get("sub")
            # When a sub-text is present, split the cell vertically;
            # otherwise the bullet text uses the whole cell.
            primary_h = item_h // 2 if has_sub else item_h
            shapes.append(
                text_box(
                    sid,
                    f"bl-{i}",
                    container.x + 120000,
                    y,
                    container.w - 240000,
                    primary_h,
                    f"・ {text}",
                    size_pt=11,
                    color=p.black,
                    font=ctx.font,
                    auto_fit=True,
                )
            )
            sid += 1
            if has_sub:
                shapes.append(
                    text_box(
                        sid,
                        f"bl-sub-{i}",
                        container.x + 320000,
                        y + primary_h,
                        container.w - 440000,
                        item_h - primary_h,
                        item["sub"],
                        size_pt=9,
                        color=p.muted,
                        font=ctx.font,
                        auto_fit=True,
                    )
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
