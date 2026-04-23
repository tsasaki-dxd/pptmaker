"""Waterfall (bridge) chart: start -> changes -> end, up/down stacked bars."""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import rect_outline, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MAX_CHANGES = 8


@register
class WaterfallRenderer(FigureRenderer):
    """Waterfall bridge chart with start bar, change deltas, and computed end bar."""

    figure_type = "waterfall"
    description = (
        "Waterfall bridge (start -> changes -> end). end value is auto-computed. "
        "content: {start: {label, value}, changes: [{label, value}], end: {label}}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {}

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        start = content.get("start")
        if not isinstance(start, dict):
            errors.append("start must be object")
        else:
            if not start.get("label"):
                errors.append("start.label required")
            if not isinstance(start.get("value"), (int, float)) or isinstance(
                start.get("value"), bool
            ):
                errors.append("start.value must be number")
        changes = content.get("changes")
        if not isinstance(changes, list) or not changes:
            errors.append("changes must be non-empty list")
        elif len(changes) > _MAX_CHANGES:
            errors.append(f"changes length must be <= {_MAX_CHANGES}")
        else:
            for i, c in enumerate(changes):
                if not isinstance(c, dict):
                    errors.append(f"changes[{i}] must be object")
                    continue
                if not c.get("label"):
                    errors.append(f"changes[{i}].label required")
                if not isinstance(c.get("value"), (int, float)) or isinstance(
                    c.get("value"), bool
                ):
                    errors.append(f"changes[{i}].value must be number")
        end = content.get("end")
        if not isinstance(end, dict) or not end.get("label"):
            errors.append("end.label required")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        start_label = str(content["start"]["label"])
        start_val = float(content["start"]["value"])
        changes: list[dict[str, Any]] = list(content["changes"])[:_MAX_CHANGES]
        end_label = str(content["end"]["label"])
        end_val = start_val + sum(float(c["value"]) for c in changes)

        n = 2 + len(changes)
        label_h = 280000
        value_h = 240000
        chart_y = container.y + value_h
        chart_h = container.h - value_h - label_h
        label_y = chart_y + chart_h

        running: list[float] = [start_val]
        v = start_val
        for c in changes:
            v += float(c["value"])
            running.append(v)
        running.append(end_val)

        lo = min(0.0, start_val, end_val, *running)
        hi = max(0.0, start_val, end_val, *running)
        rng = hi - lo
        if rng <= 0:
            rng = abs(hi) if hi != 0 else 1.0

        def _y_for(val: float) -> int:
            return chart_y + round(chart_h * (1.0 - (val - lo) / rng))

        gap = container.w // (n * 5)
        bar_w = (container.w - gap * (n + 1)) // max(1, n)

        shapes: list[str] = []
        sid = ctx.next_shape_id

        shapes.append(
            rect_outline(sid, "wf-frame", container.x, chart_y, container.w, chart_h, p.border)
        )
        sid += 1

        def _draw_bar(
            idx: int, label: str, top_val: float, bot_val: float, fill: str, kind: str
        ) -> None:
            nonlocal sid
            bx = container.x + gap + (bar_w + gap) * idx
            y_top = _y_for(max(top_val, bot_val))
            y_bot = _y_for(min(top_val, bot_val))
            h = max(y_bot - y_top, 40000)
            shapes.append(
                rect_shape(sid, f"wf-{kind}-{idx}", bx, y_top, bar_w, h, fill)
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"wf-vl-{idx}",
                    bx,
                    max(container.y, y_top - value_h),
                    bar_w,
                    value_h,
                    f"{top_val - bot_val:+.0f}" if kind == "chg" else f"{top_val:.0f}",
                    size_pt=9,
                    bold=True,
                    color=p.muted,
                    align="ctr",
                    font=ctx.font,
                )
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"wf-lb-{idx}",
                    bx,
                    label_y,
                    bar_w,
                    label_h,
                    label,
                    size_pt=9,
                    bold=True,
                    color=p.dark,
                    align="ctr",
                    font=ctx.font,
                )
            )
            sid += 1

        _draw_bar(0, start_label, start_val, 0.0, p.purple, "start")

        cursor = start_val
        for i, c in enumerate(changes):
            cv = float(c["value"])
            nxt = cursor + cv
            fill = p.green if cv >= 0 else p.amber
            _draw_bar(i + 1, str(c["label"]), nxt, cursor, fill, "chg")
            cursor = nxt

        _draw_bar(n - 1, end_label, end_val, 0.0, p.purple_dk, "end")

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
