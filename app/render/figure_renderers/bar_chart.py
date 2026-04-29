"""Bar chart figure_type — thin wrapper over the bar_chart_shape primitive.

Supports both single-series ({items: [{label, value, color?}]}) and
multi-series ({categories: [...], series: [{name, values, color?}],
mode}) input forms, since the underlying primitive already handles
both. Distinct from `stack_bar`, which is a hand-built stacked bar
specialized for a fixed series-x-categories layout — `bar_chart` is
the general primitive (grouped, stacked, stacked100, vertical, or
horizontal).
"""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import bar_chart_shape
from ..typography import TYPE_SCALE as T
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MAX_ITEMS = 12
_MAX_SERIES = 6
_MAX_CATEGORIES = 12
_MODES = ("grouped", "stacked", "stacked100")
_ORIENTATIONS = ("v", "h")


@register
class BarChartRenderer(FigureRenderer):
    """General-purpose bar chart (single- or multi-series)."""

    figure_type = "bar_chart"
    description = (
        "Bar chart. Single-series form: {items:[{label, value, color?}], "
        "orientation?}. Multi-series form: {categories:[str], series:["
        "{name, values:[number], color?}], mode? (grouped|stacked|"
        "stacked100), orientation? (v|h)}. Use `stack_bar` instead when "
        "you specifically want a stacked bar with a built-in legend block."
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "categories": ["Q1", "Q2", "Q3", "Q4"],
        "series": [
            {"name": "売上", "values": [120, 135, 142, 158]},
            {"name": "粗利", "values": [40, 48, 52, 60]},
        ],
        "mode": "grouped",
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        items = content.get("items")
        series = content.get("series")
        if items is None and series is None:
            errors.append("either `items` or `series`+`categories` required")
            return ValidationResult(False, tuple(errors))
        if items is not None and series is not None:
            errors.append("`items` and `series` are mutually exclusive")

        if items is not None:
            if not isinstance(items, list) or not items:
                errors.append("items must be non-empty list")
            elif len(items) > _MAX_ITEMS:
                errors.append(f"items length must be <= {_MAX_ITEMS}")
            else:
                for i, it in enumerate(items):
                    if not isinstance(it, dict):
                        errors.append(f"items[{i}] must be object")
                        continue
                    if not it.get("label") or not isinstance(it["label"], str):
                        errors.append(f"items[{i}].label required (str)")
                    v = it.get("value")
                    if not isinstance(v, (int, float)) or isinstance(v, bool):
                        errors.append(f"items[{i}].value must be number")

        if series is not None:
            categories = content.get("categories")
            if not isinstance(categories, list) or not categories:
                errors.append("multi-series mode requires `categories` list")
            elif len(categories) > _MAX_CATEGORIES:
                errors.append(f"categories length must be <= {_MAX_CATEGORIES}")
            if not isinstance(series, list) or not series:
                errors.append("series must be non-empty list")
            elif len(series) > _MAX_SERIES:
                errors.append(f"series length must be <= {_MAX_SERIES}")
            elif isinstance(categories, list):
                for i, s in enumerate(series):
                    if not isinstance(s, dict):
                        errors.append(f"series[{i}] must be object")
                        continue
                    if not s.get("name") or not isinstance(s["name"], str):
                        errors.append(f"series[{i}].name required (str)")
                    vals = s.get("values")
                    if not isinstance(vals, list) or len(vals) != len(categories):
                        errors.append(
                            f"series[{i}].values length must equal categories"
                        )
                        continue
                    for j, v in enumerate(vals):
                        if not isinstance(v, (int, float)) or isinstance(v, bool):
                            errors.append(f"series[{i}].values[{j}] must be number")

        mode = content.get("mode")
        if mode is not None and mode not in _MODES:
            errors.append(f"mode must be one of {_MODES}")
        orient = content.get("orientation")
        if orient is not None and orient not in _ORIENTATIONS:
            errors.append(f"orientation must be one of {_ORIENTATIONS}")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        sid = ctx.next_shape_id

        items_arg: list[tuple[str, float, str | None]] | None = None
        series_arg: list[tuple[str, list[float], str | None]] | None = None
        categories_arg: list[str] | None = None

        if content.get("items") is not None:
            items_arg = [
                (str(it["label"]), float(it["value"]), it.get("color"))
                for it in content["items"][:_MAX_ITEMS]
            ]
        else:
            categories_arg = [str(c) for c in content["categories"][:_MAX_CATEGORIES]]
            series_arg = [
                (
                    str(s["name"]),
                    [float(v) for v in s["values"][: len(categories_arg)]],
                    s.get("color"),
                )
                for s in content["series"][:_MAX_SERIES]
            ]

        xml = bar_chart_shape(
            sid,
            "bar-chart",
            container.x,
            container.y,
            container.w,
            container.h,
            items=items_arg,
            series=series_arg,
            categories=categories_arg,
            mode=str(content.get("mode") or "grouped"),
            orientation=str(content.get("orientation") or "v"),
            show_values=bool(content.get("show_values", True)),
            value_format=str(content.get("value_format") or "{:g}"),
            bar_color=p.purple,
            axis_color=p.border,
            label_color=p.dark,
            value_color=p.black,
            font_size_pt=T["label"],
            font=ctx.font,
            palette=p,
        )
        # bar_chart_shape allocates child shape IDs as sid*100+offset
        # (see shapes.py:_sub_id), so the safe next_shape_id is simply
        # the next integer — sid*100+N is always >> sid+1 anyway.
        return RenderOutput(shapes_xml=[xml] if xml else [], next_shape_id=sid + 1)
