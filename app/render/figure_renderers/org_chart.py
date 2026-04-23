"""Organizational hierarchy (up to 5 nodes, 3 levels)."""

from __future__ import annotations

from typing import Any

from ..shapes import rect_outline, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MAX_NODES = 5
_MAX_DEPTH = 3


def _compute_depth(node_id: str, parent_map: dict[str, str | None]) -> int:
    depth = 1
    cur = parent_map.get(node_id)
    while cur is not None and depth < 99:
        depth += 1
        cur = parent_map.get(cur)
    return depth


@register
class OrgChartRenderer(FigureRenderer):
    """Box-and-line org chart with up to 3 hierarchy levels."""

    figure_type = "org_chart"
    description = (
        "Org chart (max 5 nodes, 3 levels). "
        "content: {nodes: [{id, label, parent?}]}"
    )

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        nodes = content.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            return ValidationResult(False, ("nodes must be non-empty list",))
        ids: set[str] = set()
        for i, n in enumerate(nodes):
            if not isinstance(n, dict):
                errors.append(f"nodes[{i}] must be object")
                continue
            nid = n.get("id")
            if not isinstance(nid, str) or not nid:
                errors.append(f"nodes[{i}].id required")
                continue
            if not n.get("label"):
                errors.append(f"nodes[{i}].label required")
            ids.add(nid)
        roots = [n for n in nodes if isinstance(n, dict) and not n.get("parent")]
        if not roots:
            errors.append("at least one root node (no parent) required")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        raw_nodes: list[dict[str, Any]] = list(content["nodes"])
        parent_map: dict[str, str | None] = {
            n["id"]: n.get("parent") for n in raw_nodes if isinstance(n, dict)
        }
        visible = [
            n
            for n in raw_nodes
            if isinstance(n, dict)
            and _compute_depth(n["id"], parent_map) <= _MAX_DEPTH
        ][:_MAX_NODES]

        levels: dict[int, list[dict[str, Any]]] = {1: [], 2: [], 3: []}
        for n in visible:
            d = _compute_depth(n["id"], parent_map)
            levels[d].append(n)

        shapes: list[str] = []
        sid = ctx.next_shape_id

        row_gap = 60000
        row_h = (container.h - row_gap * 2) // 3
        box_h = min(row_h - 80000, 520000)
        positions: dict[str, tuple[int, int, int, int]] = {}

        for depth in (1, 2, 3):
            row = levels[depth]
            if not row:
                continue
            count = len(row)
            gap = container.w // 40
            box_w = (container.w - gap * (count - 1)) // count
            row_y = container.y + (row_h + row_gap) * (depth - 1)
            box_y = row_y + (row_h - box_h) // 2
            for i, node in enumerate(row):
                bx = container.x + (box_w + gap) * i
                positions[node["id"]] = (bx, box_y, box_w, box_h)
                fill = p.purple_bg if depth > 1 else p.purple_lt
                shapes.append(
                    rect_shape(sid, f"org-bg-{node['id']}", bx, box_y, box_w, box_h, fill)
                )
                sid += 1
                shapes.append(
                    rect_outline(
                        sid, f"org-out-{node['id']}", bx, box_y, box_w, box_h, p.border
                    )
                )
                sid += 1
                shapes.append(
                    text_box(
                        sid,
                        f"org-lbl-{node['id']}",
                        bx + 80000,
                        box_y + box_h // 2 - 180000,
                        box_w - 160000,
                        360000,
                        node["label"],
                        size_pt=11,
                        bold=True,
                        color=p.purple_dk,
                        align="ctr",
                        font=ctx.font,
                    )
                )
                sid += 1

        for node in visible:
            parent = node.get("parent")
            if not parent or parent not in positions or node["id"] not in positions:
                continue
            px, py, pw, ph = positions[parent]
            cx, cy, cw, _ = positions[node["id"]]
            parent_cx = px + pw // 2
            child_cx = cx + cw // 2
            line_top = py + ph
            line_bot = cy
            mid_y = (line_top + line_bot) // 2
            line_w = 9525
            shapes.append(
                rect_shape(
                    sid,
                    f"org-vl1-{node['id']}",
                    parent_cx - line_w // 2,
                    line_top,
                    line_w,
                    max(mid_y - line_top, 1),
                    p.muted,
                )
            )
            sid += 1
            x_left = min(parent_cx, child_cx)
            x_right = max(parent_cx, child_cx)
            if x_right > x_left:
                shapes.append(
                    rect_shape(
                        sid,
                        f"org-hl-{node['id']}",
                        x_left,
                        mid_y,
                        x_right - x_left,
                        line_w,
                        p.muted,
                    )
                )
                sid += 1
            shapes.append(
                rect_shape(
                    sid,
                    f"org-vl2-{node['id']}",
                    child_cx - line_w // 2,
                    mid_y,
                    line_w,
                    max(line_bot - mid_y, 1),
                    p.muted,
                )
            )
            sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
