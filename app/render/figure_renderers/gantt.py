"""Gantt chart with horizontal task bars over a weeks grid."""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import fit_stack, rect_outline, rect_shape, text_box
from ..typography import TYPE_SCALE as T
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

# Max tasks one Gantt slide can carry while remaining legible. Beyond
# this the blueprint LLM is instructed (via the renderer description)
# to split the chart across multiple slides, typically by `group` or
# project phase.
_MAX_TASKS = 18


@register
class GanttRenderer(FigureRenderer):
    """Gantt chart: label column (30%) + weeks grid (70%) with task bars."""

    figure_type = "gantt"
    description = (
        "Gantt chart with horizontal task bars over weeks. "
        "content: {tasks: [{label, start_week, end_week, group?}], "
        "milestones?: [{label, week}], total_weeks}. "
        f"Hard cap: {_MAX_TASKS} tasks per slide — when content has more, "
        "split into multiple gantt slides by phase or `group` (the "
        "blueprint should pre-partition; the renderer rejects content "
        "exceeding the cap rather than silently truncating)."
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
            if len(tasks) > _MAX_TASKS:
                errors.append(
                    f"tasks length {len(tasks)} exceeds max {_MAX_TASKS}; "
                    "split this gantt across multiple slides by phase or group"
                )
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

        # Header is split into two bands: milestone labels on top
        # (only when there are any milestones) and week numbers below.
        # Sharing the same band caused "判断ボード提出" / "W4" to crash
        # into each other on the user's 24-week gantt.
        week_hdr_h = 240000
        milestone_hdr_h = 280000 if milestones else 0
        header_h = milestone_hdr_h + week_hdr_h
        milestone_y = container.y
        week_hdr_y = container.y + milestone_hdr_h
        grid_y = container.y + header_h
        grid_h = container.h - header_h

        week_w = grid_w // max(1, total_weeks)
        # When a single week is too narrow to print "Wnn", thin the
        # labels out: show every 2nd / 4th / 8th depending on density.
        if week_w >= 280000:
            week_label_step = 1
        elif week_w >= 160000:
            week_label_step = 2
        elif week_w >= 100000:
            week_label_step = 4
        else:
            week_label_step = 8

        n = len(tasks)
        # row_h shrinks proportionally past natural via fit_stack so
        # 18-task gantts don't crash into the bottom of the grid.
        # min_h dropped from 140000 → 95000 so the densest case still
        # fits without squeezing labels out of legibility (95000 EMU ≈
        # 10pt line, comfortable with bar_h auto-derived from row_h).
        row_h, row_gap = fit_stack(
            container_h=grid_h,
            n=n,
            natural_h=420000,
            min_h=95000,
            gap=40000,
            min_gap=8000,
        )
        bar_h = max(60000, min(row_h - 30000, 320000))

        # Auto-shrink the per-task label font when many tasks are
        # packed in: at >12 tasks the row gets tight enough that 10pt
        # bold no longer fits cleanly inside bar_h.
        label_size = T["label"] if n <= 12 else T["caption"]

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
            # Sparsified labels: only emit on the chosen step. Header
            # box is wider than week_w when step > 1 so the label has
            # room to breathe, and auto_fit shrinks the font if it
            # still doesn't quite fit.
            if w < total_weeks and (w % week_label_step) == 0:
                hdr_w = week_w * week_label_step
                shapes.append(
                    text_box(
                        sid,
                        f"gt-whdr-{w}",
                        gx,
                        week_hdr_y,
                        hdr_w,
                        week_hdr_h - 40000,
                        f"W{w + 1}",
                        size_pt=T["caption"],
                        bold=True,
                        color=p.muted,
                        align="ctr",
                        font=ctx.font,
                        auto_fit=True,
                    )
                )
                sid += 1

        for i, task in enumerate(tasks):
            y = grid_y + (row_h + row_gap) * i
            # Label box gets the full row_h, not just bar_h — the bar
            # is centered inside the row but the label sits in the
            # left column and can use the row's full vertical space,
            # which keeps auto_fit from shrinking JP labels into
            # invisibility on dense (15-18 task) gantts.
            shapes.append(
                text_box(
                    sid,
                    f"gt-lbl-{i}",
                    container.x,
                    y,
                    label_w - 80000,
                    row_h,
                    task["label"],
                    size_pt=label_size,
                    bold=True,
                    color=p.black,
                    font=ctx.font,
                    auto_fit=False,
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

        # Milestones: vertical line through the grid + label in the
        # dedicated milestone band on top. Label width = 3 weeks wide
        # so JP labels like "判断ボード提出" fit; clamped at the right
        # edge of the grid so labels near the end don't overflow. To
        # prevent two end-of-chart milestones (e.g. weeks 17 and 21)
        # from both being clamped to the same right-edge x and stacking
        # on top of each other, sort by week and shrink each label box
        # whenever it would overlap the next one.
        ms_label_w = max(week_w * 3, 540000)
        grid_right = grid_x + grid_w
        ms_sorted = sorted(
            enumerate(milestones), key=lambda im: int(im[1]["week"])
        )
        # Compute the milestone anchor xs first so we can clamp label
        # widths to the gap between adjacent milestones.
        anchors_x = [
            grid_x + week_w * max(0, min(int(m["week"]), total_weeks))
            for _, m in ms_sorted
        ]
        for k, (j, m) in enumerate(ms_sorted):
            mx = anchors_x[k]
            shapes.append(
                rect_shape(sid, f"gt-ms-{j}", mx - 6350, grid_y, 12700, grid_h, p.amber)
            )
            sid += 1
            # Cap label width to the distance to the next milestone so
            # adjacent end-cluster labels don't collide; minimum width
            # of 360000 EMU (~0.4") so very short labels still read.
            this_label_w = ms_label_w
            if k + 1 < len(anchors_x):
                gap_to_next = anchors_x[k + 1] - mx
                this_label_w = min(ms_label_w, max(360000, gap_to_next))
            lbl_x = mx - this_label_w // 2
            if lbl_x + this_label_w > grid_right:
                lbl_x = grid_right - this_label_w
            if lbl_x < grid_x:
                lbl_x = grid_x
            shapes.append(
                text_box(
                    sid,
                    f"gt-ms-lbl-{j}",
                    lbl_x,
                    milestone_y,
                    this_label_w,
                    milestone_hdr_h - 20000 if milestone_hdr_h else 200000,
                    str(m["label"]),
                    size_pt=T["micro"],
                    bold=True,
                    color=p.amber,
                    align="ctr",
                    font=ctx.font,
                    auto_fit=True,
                )
            )
            sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
