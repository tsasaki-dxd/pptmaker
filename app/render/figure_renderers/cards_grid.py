"""Cards grid (N×M layout)."""

from __future__ import annotations

from typing import Any

from ..shapes import rect_outline, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register


@register
class CardsGridRenderer(FigureRenderer):
    figure_type = "cards_grid"
    description = (
        "Grid of uniform cards with title + body. "
        "content: {cards: [{title, body}], columns?: int (default 3)}"
    )

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        cards = content.get("cards")
        if not isinstance(cards, list) or not cards:
            return ValidationResult(False, ("cards must be non-empty list",))
        for i, c in enumerate(cards):
            if not isinstance(c, dict) or "title" not in c:
                return ValidationResult(False, (f"cards[{i}].title missing",))
        return ValidationResult(True)

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        cards = content["cards"]
        cols = int(content.get("columns", 3))
        rows = (len(cards) + cols - 1) // cols

        gap = 120000
        card_w = (container.w - gap * (cols - 1)) // cols
        card_h = (container.h - gap * (rows - 1)) // rows

        shapes: list[str] = []
        sid = ctx.next_shape_id

        for idx, card in enumerate(cards):
            col = idx % cols
            row = idx // cols
            x = container.x + (card_w + gap) * col
            y = container.y + (card_h + gap) * row

            shapes.append(rect_shape(sid, f"card-bg-{idx}", x, y, card_w, card_h, p.bg_alt))
            sid += 1
            shapes.append(rect_outline(sid, f"card-out-{idx}", x, y, card_w, card_h, p.border))
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"card-title-{idx}",
                    x + 160000,
                    y + 140000,
                    card_w - 320000,
                    400000,
                    card["title"],
                    size_pt=12,
                    bold=True,
                    color=p.purple_dk,
                    font=ctx.font,
                )
            )
            sid += 1
            if "body" in card:
                shapes.append(
                    text_box(
                        sid,
                        f"card-body-{idx}",
                        x + 160000,
                        y + 600000,
                        card_w - 320000,
                        card_h - 720000,
                        card["body"],
                        size_pt=10,
                        color=p.dark,
                        font=ctx.font,
                    )
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
