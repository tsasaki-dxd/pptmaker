"""Horizontal timeline with N steps."""

from __future__ import annotations

from typing import Any

from ..shapes import pill_label, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register


@register
class TimelineRenderer(FigureRenderer):
    figure_type = "timeline"
    description = (
        "Horizontal timeline bar with labeled steps (3-6 recommended). "
        "content: {steps: [{label, body?}], duration_label?: str}"
    )

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        steps = content.get("steps")
        if not isinstance(steps, list) or not (2 <= len(steps) <= 8):
            return ValidationResult(False, ("steps must be list of length 2-8",))
        return ValidationResult(True)

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        steps: list[dict[str, str]] = content["steps"]
        n = len(steps)

        bar_y = container.y + container.h // 3
        bar_h = 120000
        step_w = container.w // n

        shapes: list[str] = []
        sid = ctx.next_shape_id

        # Background bar
        shapes.append(rect_shape(sid, "tl-bar", container.x, bar_y, container.w, bar_h, p.purple_lt))
        sid += 1

        for i, step in enumerate(steps):
            sx = container.x + step_w * i
            pill_w = min(step_w - 80000, 900000)
            pill_h = 260000
            px = sx + (step_w - pill_w) // 2
            py = bar_y - pill_h // 2 + bar_h // 2

            shapes.append(
                pill_label(sid, f"tl-pill-{i}", px, py, pill_w, pill_h, step["label"], p.purple)
            )
            sid += 1

            body = step.get("body", "")
            if body:
                shapes.append(
                    text_box(
                        sid,
                        f"tl-body-{i}",
                        sx + 40000,
                        bar_y + bar_h + 120000,
                        step_w - 80000,
                        400000,
                        body,
                        size_pt=9,
                        color=p.dark,
                        align="ctr",
                        font=ctx.font,
                    )
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
