"""Line chart figure_type — thin wrapper over the line_chart_shape primitive."""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import line_chart_shape
from ..typography import TYPE_SCALE as T
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MAX_SERIES = 5
_MAX_POINTS = 24


@register
class LineChartRenderer(FigureRenderer):
    """Multi-series line chart sharing one x axis."""

    figure_type = "line_chart"
    description = (
        "Line chart with one or more series sharing an x axis. "
        "content: {series:[{name, values:[number], color?}], "
        "categories?:[str]}. categories aligns to value indices and "
        "renders as bottom-axis labels (omit to hide them). Each series "
        "must have at least 2 values; pad shorter series to match the "
        "longest before sending."
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "categories": ["FY22", "FY23", "FY24", "FY25", "FY26"],
        "series": [
            {"name": "売上", "values": [100, 112, 125, 138, 154]},
            {"name": "粗利", "values": [30, 35, 40, 46, 52]},
        ],
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        series = content.get("series")
        if not isinstance(series, list) or not series:
            errors.append("series must be non-empty list")
        elif len(series) > _MAX_SERIES:
            errors.append(f"series length must be <= {_MAX_SERIES}")
        else:
            for i, s in enumerate(series):
                if not isinstance(s, dict):
                    errors.append(f"series[{i}] must be object")
                    continue
                if not s.get("name") or not isinstance(s["name"], str):
                    errors.append(f"series[{i}].name required (str)")
                vals = s.get("values")
                if not isinstance(vals, list) or len(vals) < 2:
                    errors.append(f"series[{i}].values must have >= 2 numbers")
                    continue
                if len(vals) > _MAX_POINTS:
                    errors.append(f"series[{i}].values length must be <= {_MAX_POINTS}")
                for j, v in enumerate(vals):
                    if not isinstance(v, (int, float)) or isinstance(v, bool):
                        errors.append(f"series[{i}].values[{j}] must be number")
        cats = content.get("categories")
        if cats is not None:
            if not isinstance(cats, list):
                errors.append("categories must be list of str")
            else:
                for i, c in enumerate(cats):
                    if not isinstance(c, str):
                        errors.append(f"categories[{i}] must be str")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        sid = ctx.next_shape_id

        series_arg: list[tuple[str, list[float], str | None]] = [
            (
                str(s["name"]),
                [float(v) for v in s["values"][:_MAX_POINTS]],
                s.get("color"),
            )
            for s in content["series"][:_MAX_SERIES]
        ]
        cats_arg: list[str] | None = None
        if isinstance(content.get("categories"), list):
            cats_arg = [str(c) for c in content["categories"]]

        xml = line_chart_shape(
            sid,
            "line-chart",
            container.x,
            container.y,
            container.w,
            container.h,
            series=series_arg,
            x_labels=cats_arg,
            show_markers=bool(content.get("show_markers", True)),
            axis_color=p.border,
            label_color=p.dark,
            font_size_pt=T["caption"],
            font=ctx.font,
            palette=p,
        )
        return RenderOutput(shapes_xml=[xml] if xml else [], next_shape_id=sid + 1)
