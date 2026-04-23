"""Pull quote: large italic quote text with optional attribution."""

from __future__ import annotations

from typing import Any

from ..shapes import rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MAX_CHARS = 200


def _truncate(text: str, limit: int = _MAX_CHARS) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


@register
class PullQuoteRenderer(FigureRenderer):
    """Large quoted text block with attribution."""

    figure_type = "pull_quote"
    description = (
        "Pull quote with large text and optional attribution. "
        "content: {quote: str, attribution?: str}"
    )

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        quote = content.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            return ValidationResult(False, ("quote required (non-empty string)",))
        return ValidationResult(True)

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        quote = _truncate(content["quote"])
        attribution = content.get("attribution", "")

        shapes: list[str] = []
        sid = ctx.next_shape_id

        bar_w = 80000
        shapes.append(
            rect_shape(sid, "pq-bar", container.x, container.y, bar_w, container.h, p.purple)
        )
        sid += 1

        text_x = container.x + bar_w + 240000
        text_w = container.w - bar_w - 240000
        attr_h = 360000 if attribution else 0
        quote_h = container.h - attr_h - 120000

        shapes.append(
            text_box(
                sid,
                "pq-mark",
                text_x,
                container.y + 40000,
                text_w,
                320000,
                "「",
                size_pt=24,
                bold=True,
                color=p.purple_lt,
                font=ctx.font,
            )
        )
        sid += 1
        shapes.append(
            text_box(
                sid,
                "pq-quote",
                text_x,
                container.y + 240000,
                text_w,
                quote_h,
                quote,
                size_pt=18,
                bold=True,
                color=p.purple_dk,
                font=ctx.font,
            )
        )
        sid += 1

        if attribution:
            shapes.append(
                text_box(
                    sid,
                    "pq-attr",
                    text_x,
                    container.y + container.h - attr_h,
                    text_w,
                    attr_h,
                    f"— {attribution}",
                    size_pt=11,
                    color=p.muted,
                    align="r",
                    font=ctx.font,
                )
            )
            sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
