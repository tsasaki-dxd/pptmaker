"""2x2 matrix with labeled axes and four quadrant cards."""

from __future__ import annotations

from typing import Any

from ..shapes import rect_outline, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register


@register
class Matrix2x2Renderer(FigureRenderer):
    figure_type = "matrix_2x2"
    description = (
        "2x2 quadrant matrix with x/y axis labels. "
        "content: {axes: {x: {label}, y: {label}}, quadrants: [{title, body?}] x4}"
    )

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        axes = content.get("axes")
        if not isinstance(axes, dict):
            errors.append("axes must be object")
        else:
            for k in ("x", "y"):
                ax = axes.get(k)
                if not isinstance(ax, dict) or not ax.get("label"):
                    errors.append(f"axes.{k}.label required")
        quads = content.get("quadrants")
        if not isinstance(quads, list) or len(quads) != 4:
            errors.append("quadrants must be list of exactly 4")
        else:
            for i, q in enumerate(quads):
                if not isinstance(q, dict) or not q.get("title"):
                    errors.append(f"quadrants[{i}].title required")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        quads: list[dict[str, str]] = content["quadrants"]
        axes: dict[str, dict[str, str]] = content["axes"]

        axis_band = 320000
        show_axes = container.w > axis_band * 4 and container.h > axis_band * 4
        grid_x = container.x + (axis_band if show_axes else 0)
        grid_y = container.y
        grid_w = container.w - (axis_band if show_axes else 0)
        grid_h = container.h - (axis_band if show_axes else 0)

        gutter = container.w // 40
        cell_w = (grid_w - gutter) // 2
        cell_h = (grid_h - gutter) // 2

        shapes: list[str] = []
        sid = ctx.next_shape_id

        for idx in range(4):
            col = idx % 2
            row = idx // 2
            x = grid_x + (cell_w + gutter) * col
            y = grid_y + (cell_h + gutter) * row
            quad = quads[idx]

            shapes.append(rect_shape(sid, f"mx-bg-{idx}", x, y, cell_w, cell_h, p.purple_bg))
            sid += 1
            shapes.append(rect_outline(sid, f"mx-out-{idx}", x, y, cell_w, cell_h, p.border))
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"mx-title-{idx}",
                    x + 160000,
                    y + 140000,
                    cell_w - 320000,
                    400000,
                    quad["title"],
                    size_pt=12,
                    bold=True,
                    color=p.purple_dk,
                    font=ctx.font,
                )
            )
            sid += 1
            if quad.get("body"):
                shapes.append(
                    text_box(
                        sid,
                        f"mx-body-{idx}",
                        x + 160000,
                        y + 600000,
                        cell_w - 320000,
                        cell_h - 720000,
                        quad["body"],
                        size_pt=10,
                        color=p.dark,
                        font=ctx.font,
                    )
                )
                sid += 1

        if show_axes:
            shapes.append(
                text_box(
                    sid,
                    "mx-axis-x",
                    grid_x,
                    container.y + grid_h + 40000,
                    grid_w,
                    axis_band - 40000,
                    axes["x"]["label"],
                    size_pt=10,
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
                    "mx-axis-y",
                    container.x,
                    grid_y,
                    axis_band - 40000,
                    grid_h,
                    axes["y"]["label"],
                    size_pt=10,
                    bold=True,
                    color=p.muted,
                    font=ctx.font,
                )
            )
            sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
