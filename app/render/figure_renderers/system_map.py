"""System / architecture map: groups of nodes connected by typed lines.

Groups (e.g. "フロント" / "バックエンド" / "外部システム") render as
columns, each holding a small vertical stack of node cards. A flat
``connections`` list draws labeled lines between any two nodes by
ID — including across groups, which is the common case for
architecture diagrams (Web → API → DB).

Auto-routing arbitrary edges across columns is intentionally simple:
every connection is a single straight line from the right edge of
the source to the left edge of the destination (or center-to-center
for connections inside the same group). That's predictable enough
to ship without bringing in a layout library."""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import _i, _xml_escape, rect_outline, round_rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MIN_GROUPS = 2
_MAX_GROUPS = 5
_MAX_ITEMS_PER_GROUP = 6


def _line_with_optional_arrow(
    sp_id: int,
    name: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: str,
    *,
    arrow: bool = True,
    width_emu: int = 9525,
) -> str:
    bx, by = min(x1, x2), min(y1, y2)
    bw, bh = max(abs(x2 - x1), 1), max(abs(y2 - y1), 1)
    flip_h = "1" if x2 < x1 else "0"
    flip_v = "1" if y2 < y1 else "0"
    tail = '<a:tailEnd type="triangle" w="med" len="med"/>' if arrow else ""
    return (
        f'<p:cxnSp><p:nvCxnSpPr>'
        f'<p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f"<p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr>"
        f'<p:spPr>'
        f'<a:xfrm flipH="{flip_h}" flipV="{flip_v}">'
        f'<a:off x="{bx}" y="{by}"/><a:ext cx="{bw}" cy="{bh}"/>'
        f"</a:xfrm>"
        f'<a:prstGeom prst="line"><a:avLst/></a:prstGeom>'
        f'<a:ln w="{width_emu}">'
        f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        f"{tail}"
        f"</a:ln>"
        f"</p:spPr>"
        f"</p:cxnSp>"
    )


@register
class SystemMapRenderer(FigureRenderer):
    """Architecture-style map: groups (columns) × items (cards) + cross-group connections."""

    figure_type = "system_map"
    description = (
        "System / architecture map. Groups become columns; each group has up to 6 "
        "item cards stacked vertically. Connections draw arrows between item IDs. "
        "content: {groups: [{name, items: [{id, label, sub?}]}], "
        "connections: [{from, to, label?, arrow?}]}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "groups": [
            {
                "name": "フロント",
                "items": [
                    {"id": "web", "label": "Web", "sub": "Next.js"},
                    {"id": "mobile", "label": "Mobile", "sub": "iOS / Android"},
                ],
            },
            {
                "name": "バックエンド",
                "items": [
                    {"id": "api", "label": "API", "sub": "FastAPI"},
                    {"id": "worker", "label": "Worker", "sub": "SQS"},
                    {"id": "db", "label": "DB", "sub": "PostgreSQL"},
                ],
            },
            {
                "name": "外部",
                "items": [
                    {"id": "anthropic", "label": "Claude API"},
                    {"id": "ses", "label": "Email"},
                ],
            },
        ],
        "connections": [
            {"from": "web", "to": "api"},
            {"from": "mobile", "to": "api"},
            {"from": "api", "to": "db"},
            {"from": "api", "to": "worker"},
            {"from": "worker", "to": "anthropic"},
            {"from": "worker", "to": "ses"},
        ],
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        groups = content.get("groups")
        if not isinstance(groups, list) or not (_MIN_GROUPS <= len(groups) <= _MAX_GROUPS):
            return ValidationResult(
                False, (f"groups must be list of length {_MIN_GROUPS}-{_MAX_GROUPS}",)
            )
        all_ids: set[str] = set()
        for gi, g in enumerate(groups):
            if not isinstance(g, dict) or not g.get("name"):
                errors.append(f"groups[{gi}].name required")
                continue
            items = g.get("items")
            if not isinstance(items, list) or not (1 <= len(items) <= _MAX_ITEMS_PER_GROUP):
                errors.append(
                    f"groups[{gi}].items must be list of 1-{_MAX_ITEMS_PER_GROUP}"
                )
                continue
            for ii, it in enumerate(items):
                if not isinstance(it, dict):
                    errors.append(f"groups[{gi}].items[{ii}] must be object")
                    continue
                iid = it.get("id")
                if not isinstance(iid, str) or not iid:
                    errors.append(f"groups[{gi}].items[{ii}].id required")
                    continue
                if not it.get("label"):
                    errors.append(f"groups[{gi}].items[{ii}].label required")
                if iid in all_ids:
                    errors.append(f"duplicate item id: {iid}")
                all_ids.add(iid)

        connections = content.get("connections", [])
        if not isinstance(connections, list):
            errors.append("connections must be list (may be empty)")
        else:
            for ci, c in enumerate(connections):
                if not isinstance(c, dict):
                    errors.append(f"connections[{ci}] must be object")
                    continue
                if c.get("from") not in all_ids:
                    errors.append(f"connections[{ci}].from {c.get('from')!r} unknown")
                if c.get("to") not in all_ids:
                    errors.append(f"connections[{ci}].to {c.get('to')!r} unknown")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        groups: list[dict[str, Any]] = list(content["groups"])
        connections: list[dict[str, Any]] = list(content.get("connections") or [])
        n_groups = len(groups)

        gap = container.w // 60
        group_w = (container.w - gap * (n_groups - 1)) // n_groups
        title_h = 280000
        title_gap = 60000

        shapes: list[str] = []
        sid = ctx.next_shape_id

        # Per-item layout: (x, y, w, h) keyed by item id.
        item_box: dict[str, tuple[int, int, int, int]] = {}
        # Group bounds for the surrounding card.
        group_box: list[tuple[int, int, int, int, str]] = []

        for gi, g in enumerate(groups):
            gx = container.x + gi * (group_w + gap)
            gy = container.y
            gh = container.h
            group_box.append((gx, gy, group_w, gh, g["name"]))

            # Group title bar.
            shapes.append(
                round_rect_shape(
                    sid,
                    f"sysmap-gtitle-{gi}",
                    gx,
                    gy,
                    group_w,
                    title_h,
                    p.purple,
                    corner_radius_pct=12,
                )
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"sysmap-gtitle-lbl-{gi}",
                    gx + 40000,
                    gy + 20000,
                    group_w - 80000,
                    title_h - 40000,
                    g["name"],
                    size_pt=11,
                    bold=True,
                    color="FFFFFF",
                    font=ctx.font,
                    align="ctr",
                )
            )
            sid += 1

            # Group surrounding outline.
            shapes.append(
                rect_outline(
                    sid,
                    f"sysmap-gout-{gi}",
                    gx,
                    gy,
                    group_w,
                    gh,
                    p.border,
                    line_width_emu=6350,
                )
            )
            sid += 1

            items = g["items"]
            n_items = len(items)
            content_top = gy + title_h + title_gap
            content_h = gh - title_h - title_gap - 40000
            slot_h = content_h // n_items
            card_h = max(_i(slot_h * 0.78), 320000)
            slot_v_pad = (slot_h - card_h) // 2
            card_x = gx + 60000
            card_w = group_w - 120000

            for ii, it in enumerate(items):
                cy = content_top + ii * slot_h + slot_v_pad
                shapes.append(
                    round_rect_shape(
                        sid,
                        f"sysmap-card-{it['id']}",
                        card_x,
                        cy,
                        card_w,
                        card_h,
                        p.purple_bg,
                        corner_radius_pct=10,
                        line_color=p.purple_lt,
                        line_width_emu=6350,
                    )
                )
                sid += 1
                # Label + optional sub-label inside the card.
                sub = it.get("sub")
                if sub:
                    shapes.append(
                        text_box(
                            sid,
                            f"sysmap-card-lbl-{it['id']}",
                            card_x + 40000,
                            cy + 30000,
                            card_w - 80000,
                            card_h // 2 - 30000,
                            it["label"],
                            size_pt=11,
                            bold=True,
                            color=p.purple_dk,
                            font=ctx.font,
                            align="ctr",
                        )
                    )
                    sid += 1
                    shapes.append(
                        text_box(
                            sid,
                            f"sysmap-card-sub-{it['id']}",
                            card_x + 40000,
                            cy + card_h // 2,
                            card_w - 80000,
                            card_h // 2 - 30000,
                            str(sub),
                            size_pt=8,
                            color=p.muted,
                            font=ctx.font,
                            align="ctr",
                        )
                    )
                    sid += 1
                else:
                    shapes.append(
                        text_box(
                            sid,
                            f"sysmap-card-lbl-{it['id']}",
                            card_x + 40000,
                            cy + 30000,
                            card_w - 80000,
                            card_h - 60000,
                            it["label"],
                            size_pt=11,
                            bold=True,
                            color=p.purple_dk,
                            font=ctx.font,
                            align="ctr",
                            auto_fit=True,
                        )
                    )
                    sid += 1

                item_box[it["id"]] = (card_x, cy, card_w, card_h)

        for ci, c in enumerate(connections):
            sid_box = item_box.get(c["from"])
            did_box = item_box.get(c["to"])
            if sid_box is None or did_box is None:
                continue
            sx, sy, sw, sh = sid_box
            dx, dy, dw, dh = did_box
            # Same column → vertical line; otherwise horizontal between
            # the closer side edges.
            if abs((sx + sw // 2) - (dx + dw // 2)) < sw // 2:
                start = (sx + sw // 2, sy + sh)
                end = (dx + dw // 2, dy)
            elif sx < dx:
                # Source is to the left → exit right edge, enter left edge.
                start = (sx + sw, sy + sh // 2)
                end = (dx, dy + dh // 2)
            else:
                start = (sx, sy + sh // 2)
                end = (dx + dw, dy + dh // 2)
            shapes.append(
                _line_with_optional_arrow(
                    sid,
                    f"sysmap-conn-{ci}",
                    start[0],
                    start[1],
                    end[0],
                    end[1],
                    p.dark,
                    arrow=bool(c.get("arrow", True)),
                    width_emu=9525,
                )
            )
            sid += 1
            label = c.get("label")
            if label:
                mid_x = (start[0] + end[0]) // 2
                mid_y = (start[1] + end[1]) // 2
                shapes.append(
                    text_box(
                        sid,
                        f"sysmap-conn-lbl-{ci}",
                        mid_x - 360000,
                        mid_y - 120000,
                        720000,
                        240000,
                        str(label),
                        size_pt=8,
                        color=p.dark,
                        font=ctx.font,
                        align="ctr",
                    )
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
