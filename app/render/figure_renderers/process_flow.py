"""Horizontal process flow with 3-6 steps and chevron connectors."""

from __future__ import annotations

from typing import Any

from ..shapes import _i, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MIN_STEPS = 3
_MAX_STEPS = 6


def _chevron(
    sp_id: int, name: str, x: int, y: int, w: int, h: int, fill: str
) -> str:
    """Right-pointing triangular arrow (preset geometry rtTriangle rotated)."""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{name}"/>'
        f'<p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="rightArrow"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
        f'</p:spPr>'
        f'<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>'
        f'</p:sp>'
    )


@register
class ProcessFlowRenderer(FigureRenderer):
    """Horizontal 3-6 step process flow with arrow connectors."""

    figure_type = "process_flow"
    description = (
        "Horizontal process flow (3-6 steps) with pill + arrow between. "
        "content: {steps: [{label, body?}]}"
    )

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        steps = content.get("steps")
        if not isinstance(steps, list) or not (_MIN_STEPS <= len(steps) <= _MAX_STEPS):
            return ValidationResult(
                False, (f"steps must be list of length {_MIN_STEPS}-{_MAX_STEPS}",)
            )
        for i, s in enumerate(steps):
            if not isinstance(s, dict) or not s.get("label"):
                return ValidationResult(False, (f"steps[{i}].label required",))
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

        arrow_w = container.w // (n * 6)
        total_arrow = arrow_w * (n - 1)
        pill_w = (container.w - total_arrow) // n
        pill_h = min(container.h // 2, 720000)
        pill_y = container.y + (container.h - pill_h) // 3
        arrow_h = pill_h // 2
        arrow_y = pill_y + (pill_h - arrow_h) // 2

        shapes: list[str] = []
        sid = ctx.next_shape_id

        for i, step in enumerate(steps):
            sx = container.x + (pill_w + arrow_w) * i
            shapes.append(
                rect_shape(sid, f"pf-pill-{i}", sx, pill_y, pill_w, pill_h, p.purple)
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"pf-label-{i}",
                    sx + 80000,
                    pill_y + pill_h // 2 - 180000,
                    pill_w - 160000,
                    360000,
                    step["label"],
                    size_pt=12,
                    bold=True,
                    color="FFFFFF",
                    align="ctr",
                    font=ctx.font,
                )
            )
            sid += 1

            body = step.get("body", "")
            if body:
                shapes.append(
                    text_box(
                        sid,
                        f"pf-body-{i}",
                        sx + 40000,
                        pill_y + pill_h + 80000,
                        pill_w - 80000,
                        container.h - pill_h - (pill_y - container.y) - 80000,
                        body,
                        size_pt=9,
                        color=p.dark,
                        align="ctr",
                        font=ctx.font,
                    )
                )
                sid += 1

            if i < n - 1:
                ax = sx + pill_w
                shapes.append(
                    _chevron(sid, f"pf-arrow-{i}", ax, arrow_y, arrow_w, arrow_h, p.purple_lt)
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
