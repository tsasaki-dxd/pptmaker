"""Stacked bar chart (series x categories) with up to 5 series, 6 categories."""

from __future__ import annotations

from typing import Any

from ..shapes import rect_outline, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MAX_SERIES = 5
_MAX_CATEGORIES = 6


@register
class StackBarRenderer(FigureRenderer):
    """Stacked bar chart: each category is one bar stacking all series values."""

    figure_type = "stack_bar"
    description = (
        "Stacked bar chart (<=5 series, <=6 categories). "
        "content: {categories: [str], series: [{name, values: [number]}]}"
    )

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        cats = content.get("categories")
        if not isinstance(cats, list) or not cats:
            errors.append("categories must be non-empty list")
        elif len(cats) > _MAX_CATEGORIES:
            errors.append(f"categories length must be <= {_MAX_CATEGORIES}")
        else:
            for i, c in enumerate(cats):
                if not isinstance(c, str) or not c:
                    errors.append(f"categories[{i}] must be non-empty str")
        series = content.get("series")
        if not isinstance(series, list) or not series:
            errors.append("series must be non-empty list")
        elif len(series) > _MAX_SERIES:
            errors.append(f"series length must be <= {_MAX_SERIES}")
        elif isinstance(cats, list):
            for i, s in enumerate(series):
                if not isinstance(s, dict):
                    errors.append(f"series[{i}] must be object")
                    continue
                if not s.get("name"):
                    errors.append(f"series[{i}].name required")
                vals = s.get("values")
                if not isinstance(vals, list) or len(vals) != len(cats):
                    errors.append(f"series[{i}].values length must equal categories length")
                    continue
                for j, v in enumerate(vals):
                    if not isinstance(v, (int, float)) or isinstance(v, bool):
                        errors.append(f"series[{i}].values[{j}] must be number")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        cats: list[str] = list(content["categories"])[:_MAX_CATEGORIES]
        series: list[dict[str, Any]] = list(content["series"])[:_MAX_SERIES]
        n_cats = len(cats)

        legend_h = 320000
        axis_w = 480000
        chart_x = container.x + axis_w
        chart_y = container.y
        chart_w = container.w - axis_w
        chart_h = container.h - legend_h - 280000
        label_y = chart_y + chart_h
        label_h = 240000
        legend_y = label_y + label_h

        totals = [
            sum(float(s["values"][i]) for s in series if i < len(s["values"]))
            for i in range(n_cats)
        ]
        max_total = max(totals) if totals else 1.0
        if max_total <= 0:
            max_total = 1.0

        gap = chart_w // (n_cats * 4)
        bar_w = (chart_w - gap * (n_cats + 1)) // max(1, n_cats)
        palette_fills = (p.purple, p.purple_dk, p.amber, p.green, p.purple_lt)

        shapes: list[str] = []
        sid = ctx.next_shape_id

        shapes.append(
            rect_outline(sid, "sb-axis", chart_x, chart_y, chart_w, chart_h, p.border)
        )
        sid += 1

        for i in range(n_cats):
            bx = chart_x + gap + (bar_w + gap) * i
            cursor_bottom = chart_y + chart_h
            for k, s in enumerate(series):
                v = float(s["values"][i]) if i < len(s["values"]) else 0.0
                if v <= 0:
                    continue
                seg_h = round(chart_h * (v / max_total))
                if seg_h <= 0:
                    continue
                fill = palette_fills[k % len(palette_fills)]
                shapes.append(
                    rect_shape(
                        sid,
                        f"sb-seg-{i}-{k}",
                        bx,
                        cursor_bottom - seg_h,
                        bar_w,
                        seg_h,
                        fill,
                    )
                )
                sid += 1
                cursor_bottom -= seg_h
            shapes.append(
                text_box(
                    sid,
                    f"sb-cat-{i}",
                    bx,
                    label_y,
                    bar_w,
                    label_h,
                    cats[i],
                    size_pt=10,
                    bold=True,
                    color=p.muted,
                    align="ctr",
                    font=ctx.font,
                )
            )
            sid += 1

        legend_item_w = container.w // max(1, len(series))
        swatch = 180000
        for k, s in enumerate(series):
            lx = container.x + legend_item_w * k
            fill = palette_fills[k % len(palette_fills)]
            shapes.append(
                rect_shape(
                    sid,
                    f"sb-leg-sw-{k}",
                    lx,
                    legend_y + (legend_h - swatch) // 2,
                    swatch,
                    swatch,
                    fill,
                )
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"sb-leg-lbl-{k}",
                    lx + swatch + 80000,
                    legend_y,
                    legend_item_w - swatch - 80000,
                    legend_h,
                    str(s["name"]),
                    size_pt=10,
                    color=p.dark,
                    font=ctx.font,
                )
            )
            sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
