"""SWOT analysis 2x2 (strengths / weaknesses / opportunities / threats)."""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import fit_stack, pill_label, rect_outline, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_KEYS: tuple[str, ...] = ("strengths", "weaknesses", "opportunities", "threats")
_TITLES: dict[str, str] = {
    "strengths": "強み",
    "weaknesses": "弱み",
    "opportunities": "機会",
    "threats": "脅威",
}
_MAX_ITEMS = 6


@register
class SwotRenderer(FigureRenderer):
    figure_type = "swot"
    description = (
        "SWOT 2x2 grid (strengths, weaknesses, opportunities, threats). "
        "content: {strengths|weaknesses|opportunities|threats: {items: [str]}}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "strengths": {"items": ["強み1"]},
        "weaknesses": {"items": ["弱み1"]},
        "opportunities": {"items": ["機会1"]},
        "threats": {"items": ["脅威1"]},
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        for key in _KEYS:
            block = content.get(key)
            if not isinstance(block, dict):
                errors.append(f"{key} must be object")
                continue
            if not isinstance(block.get("items"), list):
                errors.append(f"{key}.items must be list")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        gutter = container.w // 40
        cell_w = (container.w - gutter) // 2
        cell_h = (container.h - gutter) // 2
        accents = (p.purple, p.amber, p.green, p.muted)

        shapes: list[str] = []
        sid = ctx.next_shape_id

        for idx, key in enumerate(_KEYS):
            col = idx % 2
            row = idx // 2
            x = container.x + (cell_w + gutter) * col
            y = container.y + (cell_h + gutter) * row
            accent = accents[idx]
            block = content[key]
            items: list[str] = list(block["items"])[:_MAX_ITEMS]

            shapes.append(rect_shape(sid, f"swot-bg-{key}", x, y, cell_w, cell_h, p.bg_alt))
            sid += 1
            shapes.append(rect_outline(sid, f"swot-out-{key}", x, y, cell_w, cell_h, p.border))
            sid += 1

            pill_w = min(cell_w - 320000, 520000)
            pill_h = 260000
            shapes.append(
                pill_label(
                    sid,
                    f"swot-pill-{key}",
                    x + 160000,
                    y + 140000,
                    pill_w,
                    pill_h,
                    _TITLES[key],
                    accent,
                    font=ctx.font,
                )
            )
            sid += 1

            if not items:
                continue
            list_y = y + 140000 + pill_h + 120000
            list_h = cell_h - (list_y - y) - 120000
            item_h, item_gap = fit_stack(
                container_h=list_h,
                n=len(items),
                natural_h=300000,
                min_h=130000,
                gap=0,
                min_gap=0,
            )
            for j, item in enumerate(items):
                shapes.append(
                    text_box(
                        sid,
                        f"swot-item-{key}-{j}",
                        x + 180000,
                        list_y + (item_h + item_gap) * j,
                        cell_w - 320000,
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
