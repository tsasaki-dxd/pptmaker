"""KPI dashboard with 3-6 metric cards (value + label + optional delta)."""

from __future__ import annotations

from typing import Any

from ..shapes import rect_outline, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MIN_METRICS = 3
_MAX_METRICS = 6


@register
class KpiDashboardRenderer(FigureRenderer):
    """Grid of KPI cards showing value, label, and optional delta."""

    figure_type = "kpi_dashboard"
    description = (
        "KPI dashboard with 3-6 metric cards. "
        "content: {metrics: [{value, label, delta?}]}"
    )

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        metrics = content.get("metrics")
        if not isinstance(metrics, list) or not (_MIN_METRICS <= len(metrics) <= _MAX_METRICS):
            return ValidationResult(
                False, (f"metrics must be list of length {_MIN_METRICS}-{_MAX_METRICS}",)
            )
        for i, m in enumerate(metrics):
            if not isinstance(m, dict):
                return ValidationResult(False, (f"metrics[{i}] must be object",))
            if not m.get("value"):
                return ValidationResult(False, (f"metrics[{i}].value required",))
            if not m.get("label"):
                return ValidationResult(False, (f"metrics[{i}].label required",))
        return ValidationResult(True)

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        metrics: list[dict[str, str]] = content["metrics"]
        n = len(metrics)
        cols = 3 if n >= 3 else n
        rows = (n + cols - 1) // cols

        gap = 120000
        card_w = (container.w - gap * (cols - 1)) // cols
        card_h = (container.h - gap * (rows - 1)) // rows

        shapes: list[str] = []
        sid = ctx.next_shape_id

        for idx, m in enumerate(metrics):
            col = idx % cols
            row = idx // cols
            x = container.x + (card_w + gap) * col
            y = container.y + (card_h + gap) * row

            shapes.append(rect_shape(sid, f"kpi-bg-{idx}", x, y, card_w, card_h, p.purple_bg))
            sid += 1
            shapes.append(
                rect_outline(sid, f"kpi-out-{idx}", x, y, card_w, card_h, p.border)
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"kpi-label-{idx}",
                    x + 160000,
                    y + 140000,
                    card_w - 320000,
                    320000,
                    m["label"],
                    size_pt=10,
                    bold=True,
                    color=p.purple_dk,
                    font=ctx.font,
                )
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"kpi-value-{idx}",
                    x + 160000,
                    y + card_h // 2 - 300000,
                    card_w - 320000,
                    600000,
                    m["value"],
                    size_pt=28,
                    bold=True,
                    color=p.purple_dk,
                    align="ctr",
                    font=ctx.font,
                )
            )
            sid += 1
            delta = m.get("delta")
            if delta:
                color = p.green if str(delta).lstrip().startswith(("+", "▲")) else p.amber
                shapes.append(
                    text_box(
                        sid,
                        f"kpi-delta-{idx}",
                        x + 160000,
                        y + card_h - 360000,
                        card_w - 320000,
                        280000,
                        delta,
                        size_pt=10,
                        bold=True,
                        color=color,
                        align="ctr",
                        font=ctx.font,
                    )
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
