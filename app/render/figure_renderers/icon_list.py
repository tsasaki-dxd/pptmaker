"""Vertical icon list: colored glyph square + title + optional body per item."""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MAX_ITEMS = 6


@register
class IconListRenderer(FigureRenderer):
    """Icon list with up to 6 items stacked vertically."""

    figure_type = "icon_list"
    description = (
        "Vertical icon list (max 6 items). "
        "content: {items: [{icon?, title, body?}]}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "items": [
            {"icon": "●", "title": "項目1", "body": "説明"},
            {"icon": "●", "title": "項目2", "body": "説明"},
        ],
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        items = content.get("items")
        if not isinstance(items, list) or not items:
            return ValidationResult(False, ("items must be non-empty list",))
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                return ValidationResult(False, (f"items[{i}] must be object",))
            if not it.get("title"):
                return ValidationResult(False, (f"items[{i}].title required",))
        return ValidationResult(True)

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        items: list[dict[str, str]] = list(content["items"])[:_MAX_ITEMS]
        n = len(items)
        accents = (p.purple, p.purple_dk, p.amber, p.green, p.purple_lt, p.muted)

        gap = 60000
        row_h = (container.h - gap * (n - 1)) // n
        icon_sz = min(row_h - 40000, 520000)

        shapes: list[str] = []
        sid = ctx.next_shape_id

        for i, item in enumerate(items):
            y = container.y + (row_h + gap) * i
            icon_x = container.x
            icon_y = y + (row_h - icon_sz) // 2
            accent = accents[i % len(accents)]

            shapes.append(
                rect_shape(
                    sid, f"il-icon-bg-{i}", icon_x, icon_y, icon_sz, icon_sz, accent
                )
            )
            sid += 1
            glyph = item.get("icon") or "●"
            shapes.append(
                text_box(
                    sid,
                    f"il-icon-ch-{i}",
                    icon_x,
                    icon_y,
                    icon_sz,
                    icon_sz,
                    glyph,
                    size_pt=18,
                    bold=True,
                    color="FFFFFF",
                    align="ctr",
                    font=ctx.font,
                )
            )
            sid += 1

            text_x = icon_x + icon_sz + 200000
            text_w = container.w - (text_x - container.x)
            body = item.get("body", "")
            title_h = row_h if not body else row_h // 2
            shapes.append(
                text_box(
                    sid,
                    f"il-title-{i}",
                    text_x,
                    y + (0 if body else (row_h - title_h) // 2),
                    text_w,
                    title_h,
                    item["title"],
                    size_pt=12,
                    bold=True,
                    color=p.purple_dk,
                    font=ctx.font,
                )
            )
            sid += 1
            if body:
                shapes.append(
                    text_box(
                        sid,
                        f"il-body-{i}",
                        text_x,
                        y + title_h,
                        text_w,
                        row_h - title_h,
                        body,
                        size_pt=10,
                        color=p.dark,
                        font=ctx.font,
                    )
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
