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
to ship without bringing in a layout library.

Visual: white item cards with a colored left bar (one accent per
group) and shadow lift; group titles use a thin underline rather
than a heavy color band so the eye lands on the cards, not on the
chrome around them.
"""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import (
    TextParagraph,
    TextRun,
    _i,
    _xml_escape,
    rect_shape,
    round_rect_shape,
    text_box,
    text_box_paragraphs,
)
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MIN_GROUPS = 2
_MAX_GROUPS = 5
_MAX_ITEMS_PER_GROUP = 6
_MAX_NOTES_PER_ITEM = 4

_GROUP_ACCENTS = ("purple_dk", "amber", "green", "purple_lt", "muted")


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
    width_emu: int = 6350,
) -> str:
    bx, by = min(x1, x2), min(y1, y2)
    bw, bh = max(abs(x2 - x1), 1), max(abs(y2 - y1), 1)
    flip_h = "1" if x2 < x1 else "0"
    flip_v = "1" if y2 < y1 else "0"
    tail = '<a:tailEnd type="triangle" w="sm" len="sm"/>' if arrow else ""
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
        "Each item card optionally carries a 1-line `sub` (tech / role) and a "
        "list of `notes` (up to 4 bullet items rendered below); when any item "
        "in a group has notes, every card in that group gets taller so the "
        "row heights stay aligned. "
        "content: {groups: [{name, items: [{id, label, sub?, notes?: [str]}]}], "
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
                    {
                        "id": "api",
                        "label": "API",
                        "sub": "FastAPI",
                        "notes": ["Cognito 認可", "RDS Proxy 経由"],
                    },
                    {
                        "id": "worker",
                        "label": "Worker",
                        "sub": "SQS",
                        "notes": ["DLQ 2回再送", "可視性 6分"],
                    },
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
                notes = it.get("notes")
                if notes is not None:
                    if not isinstance(notes, list):
                        errors.append(
                            f"groups[{gi}].items[{ii}].notes must be list"
                        )
                    elif len(notes) > _MAX_NOTES_PER_ITEM:
                        errors.append(
                            f"groups[{gi}].items[{ii}].notes must have <= "
                            f"{_MAX_NOTES_PER_ITEM} entries"
                        )

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

        gap = container.w // 30
        group_w = (container.w - gap * (n_groups - 1)) // n_groups
        title_h = _i(container.h * 0.12)
        underline_h = max(_i(0.025 * 914400), 18000)  # ~1.5pt
        accent_w = max(_i(0.05 * 914400), 36000)  # ~3pt left accent bar

        shapes: list[str] = []
        sid = ctx.next_shape_id

        item_box: dict[str, tuple[int, int, int, int]] = {}

        for gi, g in enumerate(groups):
            gx = container.x + gi * (group_w + gap)
            gy = container.y
            gh = container.h
            accent_color = getattr(p, _GROUP_ACCENTS[gi % len(_GROUP_ACCENTS)], p.purple_dk)

            # Group title — plain text + thin colored underline.
            shapes.append(
                text_box(
                    sid,
                    f"sysmap-gtitle-{gi}",
                    gx,
                    gy,
                    group_w,
                    title_h - underline_h - 30000,
                    g["name"],
                    size_pt=12,
                    bold=True,
                    color=p.black,
                    font=ctx.font,
                    align="l",
                )
            )
            sid += 1
            shapes.append(
                rect_shape(
                    sid,
                    f"sysmap-gunder-{gi}",
                    gx,
                    gy + title_h - underline_h - 20000,
                    _i(group_w * 0.45),
                    underline_h,
                    accent_color,
                )
            )
            sid += 1

            items = g["items"]
            n_items = len(items)
            content_top = gy + title_h
            content_h = gh - title_h - 60000
            slot_h = content_h // n_items
            # Cards grow if any item in this group has notes — keeps
            # rows uniform inside the group while leaving room for
            # bullet text.
            group_has_notes = any(
                isinstance(it.get("notes"), list) and any(
                    isinstance(n, str) and n.strip() for n in it["notes"]
                )
                for it in items
            )
            card_h_pct = 0.92 if group_has_notes else 0.78
            card_h = max(_i(slot_h * card_h_pct), 480000 if group_has_notes else 360000)
            slot_v_pad = max((slot_h - card_h) // 2, 0)
            card_x = gx
            card_w = group_w

            for ii, it in enumerate(items):
                cy = content_top + ii * slot_h + slot_v_pad
                # White card, no border, soft shadow.
                shapes.append(
                    round_rect_shape(
                        sid,
                        f"sysmap-card-{it['id']}",
                        card_x,
                        cy,
                        card_w,
                        card_h,
                        "FFFFFF",
                        corner_radius_pct=10,
                        shadow=True,
                    )
                )
                sid += 1
                # Colored left accent bar coding the group.
                shapes.append(
                    rect_shape(
                        sid,
                        f"sysmap-card-acc-{it['id']}",
                        card_x,
                        cy,
                        accent_w,
                        card_h,
                        accent_color,
                    )
                )
                sid += 1

                sub = it.get("sub")
                notes_raw = it.get("notes")
                notes = (
                    [str(n).strip() for n in notes_raw if isinstance(n, str) and n.strip()]
                    if isinstance(notes_raw, list)
                    else []
                )
                inset_x = card_x + accent_w + 80000
                inset_w = card_w - accent_w - 160000
                if notes:
                    # label / sub / bullet notes — all stacked. Card
                    # height was already grown when any item carried
                    # notes (see card_h compute above).
                    label_h = _i(card_h * 0.22)
                    sub_h = _i(card_h * 0.16) if sub else 0
                    notes_y = cy + 30000 + label_h + sub_h
                    notes_h = card_h - (notes_y - cy) - 20000
                    shapes.append(
                        text_box(
                            sid,
                            f"sysmap-card-lbl-{it['id']}",
                            inset_x,
                            cy + 30000,
                            inset_w,
                            label_h,
                            it["label"],
                            size_pt=12,
                            bold=True,
                            color=p.black,
                            font=ctx.font,
                            align="l",
                        )
                    )
                    sid += 1
                    if sub:
                        shapes.append(
                            text_box(
                                sid,
                                f"sysmap-card-sub-{it['id']}",
                                inset_x,
                                cy + 30000 + label_h,
                                inset_w,
                                sub_h,
                                str(sub),
                                size_pt=8,
                                color=p.muted,
                                font=ctx.font,
                                align="l",
                            )
                        )
                        sid += 1
                    paragraphs = [
                        TextParagraph(
                            runs=(
                                TextRun(
                                    text="・ " + n,
                                    size_pt=8,
                                    color=p.dark,
                                ),
                            ),
                            align="l",
                            space_before_pt=2,
                        )
                        for n in notes[:_MAX_NOTES_PER_ITEM]
                    ]
                    shapes.append(
                        text_box_paragraphs(
                            sid,
                            f"sysmap-card-notes-{it['id']}",
                            inset_x,
                            notes_y,
                            inset_w,
                            notes_h,
                            paragraphs,
                            font=ctx.font,
                            anchor="t",
                            auto_fit=True,
                        )
                    )
                    sid += 1
                elif sub:
                    shapes.append(
                        text_box(
                            sid,
                            f"sysmap-card-lbl-{it['id']}",
                            inset_x,
                            cy + 30000,
                            inset_w,
                            card_h // 2 - 30000,
                            it["label"],
                            size_pt=12,
                            bold=True,
                            color=p.black,
                            font=ctx.font,
                            align="l",
                        )
                    )
                    sid += 1
                    shapes.append(
                        text_box(
                            sid,
                            f"sysmap-card-sub-{it['id']}",
                            inset_x,
                            cy + card_h // 2,
                            inset_w,
                            card_h // 2 - 30000,
                            str(sub),
                            size_pt=8,
                            color=p.muted,
                            font=ctx.font,
                            align="l",
                        )
                    )
                    sid += 1
                else:
                    shapes.append(
                        text_box(
                            sid,
                            f"sysmap-card-lbl-{it['id']}",
                            inset_x,
                            cy + 30000,
                            inset_w,
                            card_h - 60000,
                            it["label"],
                            size_pt=12,
                            bold=True,
                            color=p.black,
                            font=ctx.font,
                            align="l",
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
            if abs((sx + sw // 2) - (dx + dw // 2)) < sw // 2:
                start = (sx + sw // 2, sy + sh)
                end = (dx + dw // 2, dy)
            elif sx < dx:
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
                    p.muted,
                    arrow=bool(c.get("arrow", True)),
                    width_emu=6350,
                )
            )
            sid += 1
            label = c.get("label")
            if label:
                mid_x = (start[0] + end[0]) // 2
                mid_y = (start[1] + end[1]) // 2
                lbl_w = 600000
                lbl_h = 220000
                # White pill backing so label doesn't sit on the line.
                shapes.append(
                    round_rect_shape(
                        sid,
                        f"sysmap-conn-pill-{ci}",
                        mid_x - lbl_w // 2,
                        mid_y - lbl_h // 2,
                        lbl_w,
                        lbl_h,
                        "FFFFFF",
                        corner_radius_pct=50,
                    )
                )
                sid += 1
                shapes.append(
                    text_box(
                        sid,
                        f"sysmap-conn-lbl-{ci}",
                        mid_x - lbl_w // 2,
                        mid_y - lbl_h // 2,
                        lbl_w,
                        lbl_h,
                        str(label),
                        size_pt=8,
                        color=p.dark,
                        font=ctx.font,
                        align="ctr",
                    )
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
