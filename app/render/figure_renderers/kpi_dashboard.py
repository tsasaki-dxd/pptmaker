"""KPI dashboard with 3-6 metric cards (value + label + optional delta)."""

from __future__ import annotations

from typing import Any, ClassVar

from ..icon_renderer import is_known as _icon_known
from ..shapes import icon_pic, rect_outline, rect_shape, text_box
from ..typography import TYPE_SCALE as T
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MIN_METRICS = 3
_MAX_METRICS = 6

# Default icons cycled through KPI cards when the blueprint doesn't
# specify an `icon` field per metric. Picked for general business
# context — gauges, growth, targets — and intentionally non-redundant.
_DEFAULT_ICON_CYCLE: tuple[str, ...] = (
    "trending-up",
    "target",
    "gauge",
    "activity",
    "award",
    "zap",
)


@register
class KpiDashboardRenderer(FigureRenderer):
    """Grid of KPI cards showing value, label, and optional delta."""

    figure_type = "kpi_dashboard"
    description = (
        "KPI dashboard with 3-6 metric cards. "
        "content: {metrics: [{value, label, delta?}]}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "metrics": [
            {"value": "120", "label": "売上", "delta": "+12%"},
            {"value": "85%", "label": "満足度", "delta": "+3%"},
            {"value": "1.2s", "label": "応答", "delta": "-0.1s"},
        ],
    }

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

            # Top-left icon. Use the metric's `icon` field if it names a
            # known Lucide icon, otherwise cycle through default business
            # icons. Skipped silently when no MediaRegistry was threaded
            # through (test environments) — the rest of the card still
            # renders cleanly.
            icon_size = 320000
            icon_pad = 160000
            icon_name = (
                m.get("icon")
                if isinstance(m.get("icon"), str) and _icon_known(m["icon"])
                else _DEFAULT_ICON_CYCLE[idx % len(_DEFAULT_ICON_CYCLE)]
            )
            label_x = x + icon_pad
            if ctx.media is not None:
                try:
                    shapes.append(
                        icon_pic(
                            sid,
                            icon_name,
                            ctx.media,
                            ctx.slide_index or 0,
                            x + icon_pad,
                            y + icon_pad,
                            icon_size,
                            icon_size,
                            color=p.purple_dk,
                        )
                    )
                    sid += 1
                    label_x = x + icon_pad + icon_size + 100000
                except (ValueError, RuntimeError):
                    # Bad icon name or cairosvg unavailable: fall through
                    # to the icon-less layout.
                    pass

            shapes.append(
                text_box(
                    sid,
                    f"kpi-label-{idx}",
                    label_x,
                    y + 140000,
                    card_w - (label_x - x) - 160000,
                    icon_size,
                    m["label"],
                    size_pt=T["label"],
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
                    size_pt=T["h1"],
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
                        size_pt=T["caption"],
                        bold=True,
                        color=color,
                        align="ctr",
                        font=ctx.font,
                    )
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
