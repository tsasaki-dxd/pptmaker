"""Pie chart figure_type — pie_chart_shape primitive + side legend.

The underlying primitive intentionally draws no labels (overlap
heuristics inside a deterministic emitter are a tar pit). This
renderer composes the pie on the left and a swatch + label + share%
legend on the right, so blueprint output is readable without the
caller having to compose pills around the disk themselves.
"""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import pie_chart_shape, rect_shape, text_box
from ..typography import TYPE_SCALE as T
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MAX_SLICES = 8


def _palette_color(idx: int, palette: Any) -> str:
    fills = (
        palette.purple,
        palette.purple_dk,
        palette.amber,
        palette.green,
        palette.purple_lt,
        palette.muted,
        palette.dark,
        palette.black,
    )
    return fills[idx % len(fills)]


@register
class PieChartRenderer(FigureRenderer):
    """Pie chart with right-side legend (swatch + label + %)."""

    figure_type = "pie_chart"
    description = (
        "Pie chart with a right-side legend. content: {slices:["
        "{label, value, color?}]}. Values must be positive; the legend "
        "shows each slice's percentage of the total."
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "slices": [
            {"label": "サブスク", "value": 60},
            {"label": "従量", "value": 25},
            {"label": "コンサル", "value": 15},
        ],
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        slices = content.get("slices")
        if not isinstance(slices, list) or not slices:
            errors.append("slices must be non-empty list")
        elif len(slices) > _MAX_SLICES:
            errors.append(f"slices length must be <= {_MAX_SLICES}")
        else:
            total_positive = 0.0
            for i, s in enumerate(slices):
                if not isinstance(s, dict):
                    errors.append(f"slices[{i}] must be object")
                    continue
                if not s.get("label") or not isinstance(s["label"], str):
                    errors.append(f"slices[{i}].label required (str)")
                v = s.get("value")
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    errors.append(f"slices[{i}].value must be number")
                elif v <= 0:
                    errors.append(f"slices[{i}].value must be positive")
                else:
                    total_positive += float(v)
            if not errors and total_positive <= 0:
                errors.append("at least one slice must have value > 0")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        slices: list[dict[str, Any]] = list(content["slices"])[:_MAX_SLICES]
        total = sum(float(s["value"]) for s in slices)

        # Pie occupies the left ~55%, sized as a square inside that
        # column so it doesn't squash on tall containers; legend gets
        # the remaining width.
        pie_col_w = int(container.w * 0.55)
        legend_w = container.w - pie_col_w - 200000
        pie_size = min(pie_col_w - 80000, container.h - 80000)
        pie_x = container.x + (pie_col_w - pie_size) // 2
        pie_y = container.y + (container.h - pie_size) // 2
        legend_x = container.x + pie_col_w + 200000

        sid = ctx.next_shape_id
        shapes: list[str] = []

        slice_args: list[tuple[str, float, str | None]] = []
        for i, s in enumerate(slices):
            color = s.get("color") or _palette_color(i, p)
            slice_args.append((str(s["label"]), float(s["value"]), color))

        pie_xml = pie_chart_shape(
            sid,
            "pie-chart",
            pie_x,
            pie_y,
            pie_size,
            pie_size,
            slices=slice_args,
            palette=p,
        )
        if pie_xml:
            shapes.append(pie_xml)
        sid += 1

        # Legend rows: square swatch, label, percentage. Sized to fit
        # all slices in the legend column with a comfortable gap.
        n = len(slices)
        row_h = min(360000, container.h // max(n, 1))
        swatch = min(row_h - 80000, 200000)
        legend_y0 = container.y + (container.h - row_h * n) // 2
        for i, s in enumerate(slices):
            ry = legend_y0 + row_h * i
            color = s.get("color") or _palette_color(i, p)
            shapes.append(
                rect_shape(
                    sid,
                    f"pc-leg-sw-{i}",
                    legend_x,
                    ry + (row_h - swatch) // 2,
                    swatch,
                    swatch,
                    color,
                )
            )
            sid += 1
            label_x = legend_x + swatch + 100000
            pct = (float(s["value"]) / total * 100.0) if total > 0 else 0.0
            shapes.append(
                text_box(
                    sid,
                    f"pc-leg-lbl-{i}",
                    label_x,
                    ry,
                    legend_w - swatch - 100000 - 600000,
                    row_h,
                    str(s["label"]),
                    size_pt=T["label"],
                    color=p.dark,
                    font=ctx.font,
                    auto_fit=True,
                )
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"pc-leg-pct-{i}",
                    legend_x + legend_w - 600000,
                    ry,
                    600000,
                    row_h,
                    f"{pct:.0f}%",
                    size_pt=T["body_lg"],
                    bold=True,
                    color=p.purple_dk,
                    align="r",
                    font=ctx.font,
                )
            )
            sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
