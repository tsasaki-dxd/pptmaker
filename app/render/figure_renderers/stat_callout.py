"""Big number callout (for cost summaries, KPIs)."""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register


@register
class StatCalloutRenderer(FigureRenderer):
    figure_type = "stat_callout"
    description = (
        "Big number / metric callout. "
        "content: {value: str, label: str, note?: str}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "value": "42%",
        "label": "成長率",
        "note": "前年比",
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        for k in ("value", "label"):
            if not content.get(k):
                return ValidationResult(False, (f"{k} required",))
        return ValidationResult(True)

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        shapes: list[str] = []
        sid = ctx.next_shape_id

        shapes.append(
            rect_shape(sid, "stat-bg", container.x, container.y, container.w, container.h, p.purple_bg)
        )
        sid += 1
        shapes.append(
            text_box(
                sid,
                "stat-label",
                container.x + 200000,
                container.y + 180000,
                container.w - 400000,
                400000,
                content["label"],
                size_pt=12,
                bold=True,
                color=p.purple_dk,
                font=ctx.font,
            )
        )
        sid += 1
        shapes.append(
            text_box(
                sid,
                "stat-value",
                container.x + 200000,
                container.y + container.h // 2 - 400000,
                container.w - 400000,
                800000,
                content["value"],
                size_pt=36,
                bold=True,
                color=p.purple_dk,
                align="ctr",
                font=ctx.font,
            )
        )
        sid += 1
        if content.get("note"):
            shapes.append(
                text_box(
                    sid,
                    "stat-note",
                    container.x + 200000,
                    container.y + container.h - 400000,
                    container.w - 400000,
                    300000,
                    content["note"],
                    size_pt=9,
                    color=p.muted,
                    align="ctr",
                    font=ctx.font,
                )
            )
            sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
