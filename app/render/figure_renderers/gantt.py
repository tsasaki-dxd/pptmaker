"""Gantt chart with horizontal task bars over a weeks grid."""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import rect_outline, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MAX_TASKS = 10


@register
class GanttRenderer(FigureRenderer):
    """Gantt chart: label column (30%) + weeks grid (70%) with task bars."""

    figure_type = "gantt"
    description = (
        "Gantt chart with horizontal task bars over weeks. "
        "content: {tasks: [{label, start_week, end_week, group?}], "
        "milestones?: [{label, week}], total_weeks}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {}

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        total_weeks = content.get("total_weeks")
        if not isinstance(total_weeks, int) or total_weeks < 1:
            errors.append("total_weeks must be positive int")
        tasks = content.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            errors.append("tasks must be non-empty list")
        else:
            for i, t in enumerate(tasks):
                if not isinstance(t, dict):
                    errors.append(f"tasks[{i}] must be object")
                    continue
                if not t.get("label"):
                    errors.append(f"tasks[{i}].label required")
                sw = t.get("start_week")
                ew = t.get("end_week")
                if not isinstance(sw, int) or not isinstance(ew, int):
                    errors.append(f"tasks[{i}].start_week/end_week must be int")
                elif sw < 0 or ew < sw:
                    errors.append(f"tasks[{i}] start_week <= end_week required")
        milestones = content.get("milestones")
        if milestones is not None:
            if not isinstance(milestones, list):
                errors.append("milestones must be list")
            else:
                for i, m in enumerate(milestones):
                    if not isinstance(m, dict) or not m.get("label"):
                        errors.append(f"milestones[{i}].label required")
                    elif not isinstance(m.get("week"), int):
                        errors.append(f"milestones[{i}].week must be int")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        tasks: list[dict[str, Any]] = list(content["tasks"])[:_MAX_TASKS]
        total_weeks: int = int(content["total_weeks"])
        milestones: list[dict[str, Any]] = list(content.get("milestones") or [])

        label_w = container.w * 30 // 100
        grid_x = container.x + label_w
        grid_w = container.w - label_w
        header_h = 280000
        grid_y = container.y + header_h
        grid_h = container.h - header_h

        week_w = grid_w // max(1, total_weeks)
        n = len(tasks)
        gap = 40000
        row_h = (grid_h - gap * max(0, n - 1)) // max(1, n)
        bar_h = min(row_h - 40000, 320000)

        group_palette = (p.purple, p.purple_dk, p.amber, p.green, p.purple_lt, p.muted)
        group_colors: dict[str, str] = {}

        def _group_color(group: str | None) -> str:
            if not group:
                return p.purple
            if group not in group_colors:
                group_colors[group] = group_palette[len(group_colors) % len(group_palette)]
            return group_colors[group]

        shapes: list[str] = []
        sid = ctx.next_shape_id

        shapes.append(
            rect_shape(sid, "gt-grid-bg", grid_x, grid_y, grid_w, grid_h, p.bg_alt)
        )
        sid += 1
        shapes.append(
            rect_outline(sid, "gt-grid-out", grid_x, grid_y, grid_w, grid_h, p.border)
        )
        sid += 1

        for w in range(total_weeks + 1):
            gx = grid_x + week_w * w
            shapes.append(
                rect_shape(sid, f"gt-wline-{w}", gx, grid_y, 9525, grid_h, p.border)
            )
            sid += 1
            if w < total_weeks:
                shapes.append(
                    text_box(
                        sid,
                        f"gt-whdr-{w}",
                        gx,
                        container.y,
                        week_w,
                        header_h - 40000,
                        f"W{w + 1}",
                        size_pt=9,
                        bold=True,
                        color=p.muted,
                        align="ctr",
                        font=ctx.font,
                    )
                )
                sid += 1

        for i, task in enumerate(tasks):
            y = grid_y + (row_h + gap) * i
            shapes.append(
                text_box(
                    sid,
                    f"gt-lbl-{i}",
                    container.x,
                    y + (row_h - bar_h) // 2,
                    label_w - 80000,
                    bar_h,
                    task["label"],
                    size_pt=10,
                    bold=True,
                    color=p.black,
                    font=ctx.font,
                )
            )
            sid += 1
            sw = max(0, min(int(task["start_week"]), total_weeks))
            ew = max(sw, min(int(task["end_week"]), total_weeks))
            bx = grid_x + week_w * sw
            bw = max(week_w // 4, week_w * (ew - sw))
            by = y + (row_h - bar_h) // 2
            fill = _group_color(task.get("group"))
            shapes.append(
                rect_shape(sid, f"gt-bar-{i}", bx, by, bw, bar_h, fill)
            )
            sid += 1

        for j, m in enumerate(milestones):
            wk = max(0, min(int(m["week"]), total_weeks))
            mx = grid_x + week_w * wk
            shapes.append(
                rect_shape(sid, f"gt-ms-{j}", mx - 6350, grid_y, 12700, grid_h, p.amber)
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"gt-ms-lbl-{j}",
                    mx,
                    container.y,
                    week_w * 2,
                    header_h - 40000,
                    str(m["label"]),
                    size_pt=8,
                    bold=True,
                    color=p.amber,
                    font=ctx.font,
                )
            )
            sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
