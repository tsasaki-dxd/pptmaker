"""Horizontal process flow with 3-6 steps and chevron connectors."""

from __future__ import annotations

from typing import Any, ClassVar

from ..icon_renderer import is_known as _icon_known
from ..shapes import _i, icon_pic, rect_shape, text_box
from ..typography import TYPE_SCALE as T
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MIN_STEPS = 3
_MAX_STEPS = 6

# First step → "rocket" (kickoff), middle → "settings" / "workflow" /
# "zap", last → "check-circle" (done). Cycled by step position so any
# 3-6 step flow gets reasonable coverage without per-step hints.
_STEP_ICON_CYCLE: tuple[str, ...] = (
    "rocket",
    "settings",
    "workflow",
    "zap",
    "refresh-cw",
    "check-circle",
)


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
    input_schema_example: ClassVar[dict[str, Any]] = {
        "steps": [
            {"label": "計画", "body": "要件整理"},
            {"label": "実行", "body": "開発"},
            {"label": "完了", "body": "納品"},
        ],
    }

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

            # Per-step icon at the pill's left edge. Honors a per-step
            # `icon` field if it names a known Lucide icon, otherwise
            # cycles through the default sequence.
            step_icon_size = min(pill_h - 120000, 360000)
            icon_pad = 60000
            label_left = sx + 80000
            icon_name = (
                step.get("icon")
                if isinstance(step.get("icon"), str) and _icon_known(step["icon"])
                else _STEP_ICON_CYCLE[i % len(_STEP_ICON_CYCLE)]
            )
            if ctx.media is not None:
                try:
                    shapes.append(
                        icon_pic(
                            sid,
                            icon_name,
                            ctx.media,
                            ctx.slide_index or 0,
                            sx + icon_pad,
                            pill_y + (pill_h - step_icon_size) // 2,
                            step_icon_size,
                            step_icon_size,
                            color="FFFFFF",
                        )
                    )
                    sid += 1
                    label_left = sx + icon_pad + step_icon_size + 60000
                except (ValueError, RuntimeError):
                    pass

            shapes.append(
                text_box(
                    sid,
                    f"pf-label-{i}",
                    label_left,
                    pill_y + pill_h // 2 - 180000,
                    sx + pill_w - label_left - 80000,
                    360000,
                    step["label"],
                    size_pt=T["body_lg"],
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
                        size_pt=T["caption"],
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
