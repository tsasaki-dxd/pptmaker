"""Stakeholder value-flow diagram (商流 / 金流 / 情報流).

Multiple actors (顧客 / 自社 / パートナー / サプライヤ etc.) arranged on a
regular polygon, with directional arrows between them carrying a
short label and a flow ``kind`` (money / goods / info / contract)
that drives arrow color. Bidirectional pairs are detected and the
two arrows offset perpendicular to each other so they don't overlap.

This is intentionally distinct from system_map: actors here are
peers in a commercial relationship (not architectural components),
arrows are typed (not all "data flows the same direction"), and the
layout is symmetry-driven rather than column-based.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar

from ..shapes import _i, _xml_escape, round_rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MIN_ACTORS = 2
_MAX_ACTORS = 6
_FLOW_KINDS = ("money", "goods", "info", "contract")
_CONNECTOR_STYLES = ("straight", "curved", "bent")
_PRST_BY_STYLE = {
    "straight": "line",
    # bentConnector3 = single right-angle bend between two endpoints
    # (orthogonal L-shape). Direction is inferred from the bbox
    # aspect, plus our existing flipH / flipV.
    "bent": "bentConnector3",
    # curvedConnector3 = smooth single-inflection curve. Reads better
    # than a straight line when actors sit on a polygon and direct
    # lines would cross each other.
    "curved": "curvedConnector3",
}


def _arrow(
    sp_id: int,
    name: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: str,
    *,
    width_emu: int = 9525,
    head_size: str = "med",
    style: str = "straight",
) -> str:
    bx, by = min(x1, x2), min(y1, y2)
    bw, bh = max(abs(x2 - x1), 1), max(abs(y2 - y1), 1)
    flip_h = "1" if x2 < x1 else "0"
    flip_v = "1" if y2 < y1 else "0"
    prst = _PRST_BY_STYLE.get(style, "line")
    return (
        f'<p:cxnSp><p:nvCxnSpPr>'
        f'<p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f"<p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr>"
        f'<p:spPr>'
        f'<a:xfrm flipH="{flip_h}" flipV="{flip_v}">'
        f'<a:off x="{bx}" y="{by}"/><a:ext cx="{bw}" cy="{bh}"/>'
        f"</a:xfrm>"
        f'<a:prstGeom prst="{prst}"><a:avLst/></a:prstGeom>'
        f'<a:ln w="{width_emu}">'
        f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        f'<a:tailEnd type="triangle" w="{head_size}" len="{head_size}"/>'
        f"</a:ln>"
        f"</p:spPr>"
        f"</p:cxnSp>"
    )


def _rect_edge_intersect(
    cx: int, cy: int, w: int, h: int, ax: int, ay: int
) -> tuple[int, int]:
    """Where the line from rect center (cx, cy) toward external point
    (ax, ay) hits the rect perimeter."""
    dx = ax - cx
    dy = ay - cy
    if dx == 0 and dy == 0:
        return cx, cy
    hx = w / 2
    hy = h / 2
    abs_dx = abs(dx) or 1
    abs_dy = abs(dy) or 1
    scale = hx / abs_dx if abs_dx * hy >= abs_dy * hx else hy / abs_dy
    return cx + int(dx * scale), cy + int(dy * scale)


@register
class ValueFlowRenderer(FigureRenderer):
    """Actor cards on a regular polygon + typed labeled arrows."""

    figure_type = "value_flow"
    description = (
        "Stakeholder value-flow diagram. 2-6 actors auto-positioned on "
        "a regular polygon (line / triangle / square / pentagon / hexagon). "
        "Flows are directed arrows colored by kind: money (amber), "
        "goods (purple), info (muted), contract (green). Mark one actor "
        "as primary=true to render it filled in the brand color. "
        "Bidirectional flows render as two parallel arrows so neither "
        "label sits on top of the other. Each actor accepts an optional "
        "1-2 line `note` (business-model fact / scale / regulation) "
        "rendered below the role; cards grow taller automatically when "
        "any actor has a note so the layout stays uniform. "
        "`connector_style` defaults to 'curved' (smooth single-inflection "
        "curves which read better than straight lines on a polygon "
        "layout); use 'bent' for orthogonal L-shape connectors or "
        "'straight' to revert to direct lines. "
        "content: {actors: [{id, label, role?, primary?, note?}], "
        "flows: [{from, to, label?, kind?}], "
        "connector_style?: 'straight'|'curved'|'bent'}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "actors": [
            {
                "id": "cust",
                "label": "顧客",
                "role": "個人 / 法人",
                "note": "国内 50万 MAU",
            },
            {
                "id": "us",
                "label": "自社",
                "role": "プラットフォーム",
                "primary": True,
                "note": "GMV の 12% が手数料収入",
            },
            {
                "id": "ptr",
                "label": "出店者",
                "role": "サプライヤ",
                "note": "1,200 事業者",
            },
        ],
        "flows": [
            {"from": "cust", "to": "us", "label": "利用料", "kind": "money"},
            {"from": "us", "to": "cust", "label": "サービス提供", "kind": "goods"},
            {"from": "us", "to": "ptr", "label": "売上手数料", "kind": "money"},
            {"from": "ptr", "to": "us", "label": "在庫データ", "kind": "info"},
        ],
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        actors = content.get("actors")
        if not isinstance(actors, list) or not (_MIN_ACTORS <= len(actors) <= _MAX_ACTORS):
            return ValidationResult(
                False, (f"actors must be list of length {_MIN_ACTORS}-{_MAX_ACTORS}",)
            )
        ids: set[str] = set()
        for i, a in enumerate(actors):
            if not isinstance(a, dict):
                errors.append(f"actors[{i}] must be object")
                continue
            aid = a.get("id")
            if not isinstance(aid, str) or not aid:
                errors.append(f"actors[{i}].id required")
                continue
            if not a.get("label"):
                errors.append(f"actors[{i}].label required")
            if aid in ids:
                errors.append(f"duplicate actor id: {aid}")
            ids.add(aid)

        flows = content.get("flows", [])
        if not isinstance(flows, list):
            errors.append("flows must be list (may be empty)")
        else:
            for fi, f in enumerate(flows):
                if not isinstance(f, dict):
                    errors.append(f"flows[{fi}] must be object")
                    continue
                if f.get("from") not in ids:
                    errors.append(f"flows[{fi}].from {f.get('from')!r} unknown")
                if f.get("to") not in ids:
                    errors.append(f"flows[{fi}].to {f.get('to')!r} unknown")
                if f.get("from") == f.get("to"):
                    errors.append(f"flows[{fi}] cannot self-loop")
                kind = f.get("kind")
                if kind is not None and kind not in _FLOW_KINDS:
                    errors.append(
                        f"flows[{fi}].kind must be one of {list(_FLOW_KINDS)}"
                    )

        cs = content.get("connector_style")
        if cs is not None and cs not in _CONNECTOR_STYLES:
            errors.append(
                f"connector_style must be one of {list(_CONNECTOR_STYLES)}"
            )
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        actors: list[dict[str, Any]] = list(content["actors"])
        flows: list[dict[str, Any]] = list(content.get("flows") or [])
        n = len(actors)
        connector_style = str(content.get("connector_style") or "curved").lower()
        if connector_style not in _CONNECTOR_STYLES:
            connector_style = "curved"

        canvas_min = min(container.w, container.h)
        cx = container.x + container.w // 2
        cy = container.y + container.h // 2

        # Cards grow when any actor carries a `note` so the longer
        # description has room without crashing into the role line.
        any_note = any(
            isinstance(a.get("note"), str) and a["note"].strip() for a in actors
        )
        card_w = _i(canvas_min * 0.42)
        card_h = _i(canvas_min * (0.30 if any_note else 0.22))

        # Polygon radius. For 2 actors we use horizontal placement with
        # a generous gap; for 3+ a polygon centered on the canvas.
        margin = _i(canvas_min * 0.04)
        radius_x = max(container.w // 2 - card_w // 2 - margin, card_w)
        radius_y = max(container.h // 2 - card_h // 2 - margin, card_h)

        # Actor positions (top-left of each card).
        pos: dict[str, tuple[int, int, int, int]] = {}  # id → (x, y, w, h)

        if n == 2:
            # Two actors face each other left-right.
            ax_left = container.x + margin
            ax_right = container.x + container.w - margin - card_w
            y = cy - card_h // 2
            pos[actors[0]["id"]] = (ax_left, y, card_w, card_h)
            pos[actors[1]["id"]] = (ax_right, y, card_w, card_h)
        else:
            # Polygon: start at top (-90°) and walk clockwise.
            for i, a in enumerate(actors):
                angle_deg = -90 + (360.0 * i / n)
                rad = math.radians(angle_deg)
                acx = cx + int(radius_x * math.cos(rad))
                acy = cy + int(radius_y * math.sin(rad))
                ax = acx - card_w // 2
                ay = acy - card_h // 2
                # Clamp to container so cards don't bleed off the edge.
                ax = max(container.x, min(ax, container.x + container.w - card_w))
                ay = max(container.y, min(ay, container.y + container.h - card_h))
                pos[a["id"]] = (ax, ay, card_w, card_h)

        # Detect bidirectional pairs so we can offset their arrows.
        flow_pairs: dict[tuple[str, str], int] = {}  # canonical (lo, hi) → count
        for f in flows:
            key = tuple(sorted((f["from"], f["to"])))
            flow_pairs[key] = flow_pairs.get(key, 0) + 1

        kind_color = {
            "money": p.amber,
            "goods": p.purple_dk,
            "info": p.muted,
            "contract": p.green,
        }

        sid = ctx.next_shape_id
        shapes: list[str] = []

        # Draw arrows first so they tuck under the actor cards.
        offset_step = _i(canvas_min * 0.025)
        # Track per-pair offset state: how many we've already placed.
        pair_drawn: dict[tuple[str, str], int] = {}

        for fi, f in enumerate(flows):
            src, dst = f["from"], f["to"]
            sx, sy, sw, sh = pos[src]
            dx, dy, dw, dh = pos[dst]
            scx, scy = sx + sw // 2, sy + sh // 2
            dcx, dcy = dx + dw // 2, dy + dh // 2

            start = _rect_edge_intersect(scx, scy, sw, sh, dcx, dcy)
            end = _rect_edge_intersect(dcx, dcy, dw, dh, scx, scy)

            # If this pair has bidirectional flows, offset the second
            # one (and onwards) perpendicular to the line.
            pair_key = tuple(sorted((src, dst)))
            already = pair_drawn.get(pair_key, 0)
            pair_drawn[pair_key] = already + 1
            if flow_pairs[pair_key] >= 2:
                # Compute perpendicular unit vector and offset.
                vx, vy = end[0] - start[0], end[1] - start[1]
                length = math.hypot(vx, vy) or 1.0
                # Rotate 90° clockwise relative to direction of travel.
                px, py = vy / length, -vx / length
                # Sign alternates so the two arrows of a pair don't
                # overlap each other.
                sign = 1 if already % 2 == 0 else -1
                ox = int(px * offset_step * sign)
                oy = int(py * offset_step * sign)
                start = (start[0] + ox, start[1] + oy)
                end = (end[0] + ox, end[1] + oy)

            kind = f.get("kind") or "info"
            color = kind_color.get(kind, p.muted)
            shapes.append(
                _arrow(
                    sid,
                    f"vf-flow-{fi}",
                    start[0],
                    start[1],
                    end[0],
                    end[1],
                    color,
                    width_emu=12700,
                    head_size="med",
                    style=connector_style,
                )
            )
            sid += 1

            label = f.get("label")
            if label:
                # White pill ~1/3 along the arrow toward destination.
                lx = start[0] + (end[0] - start[0]) * 35 // 100
                ly = start[1] + (end[1] - start[1]) * 35 // 100
                lbl_w = 700000
                lbl_h = 240000
                shapes.append(
                    round_rect_shape(
                        sid,
                        f"vf-flow-pill-{fi}",
                        lx - lbl_w // 2,
                        ly - lbl_h // 2,
                        lbl_w,
                        lbl_h,
                        "FFFFFF",
                        corner_radius_pct=50,
                        line_color=color,
                        line_width_emu=6350,
                    )
                )
                sid += 1
                shapes.append(
                    text_box(
                        sid,
                        f"vf-flow-lbl-{fi}",
                        lx - lbl_w // 2,
                        ly - lbl_h // 2,
                        lbl_w,
                        lbl_h,
                        str(label),
                        size_pt=9,
                        color=p.dark,
                        font=ctx.font,
                        align="ctr",
                    )
                )
                sid += 1

        # Actor cards on top of arrows.
        for a in actors:
            ax, ay, aw, ah = pos[a["id"]]
            primary = bool(a.get("primary"))
            fill = p.purple_dk if primary else "FFFFFF"
            shapes.append(
                round_rect_shape(
                    sid,
                    f"vf-actor-{a['id']}",
                    ax,
                    ay,
                    aw,
                    ah,
                    fill,
                    corner_radius_pct=12,
                    shadow=True,
                )
            )
            sid += 1

            text_color = "FFFFFF" if primary else p.black
            sub_color = "FFFFFF" if primary else p.muted
            role = a.get("role")
            note_raw = a.get("note")
            note = (
                note_raw.strip()
                if isinstance(note_raw, str) and note_raw.strip()
                else ""
            )
            if note:
                # Three-line layout: label / role / note. role can be
                # empty in which case the role band collapses but the
                # note still sits in the lower third.
                label_h = _i(ah * 0.35)
                role_h = _i(ah * 0.18) if role else 0
                shapes.append(
                    text_box(
                        sid,
                        f"vf-actor-lbl-{a['id']}",
                        ax + 40000,
                        ay + 30000,
                        aw - 80000,
                        label_h,
                        a["label"],
                        size_pt=14,
                        bold=True,
                        color=text_color,
                        font=ctx.font,
                        align="ctr",
                    )
                )
                sid += 1
                if role:
                    shapes.append(
                        text_box(
                            sid,
                            f"vf-actor-role-{a['id']}",
                            ax + 40000,
                            ay + 30000 + label_h,
                            aw - 80000,
                            role_h,
                            str(role),
                            size_pt=9,
                            color=sub_color,
                            font=ctx.font,
                            align="ctr",
                        )
                    )
                    sid += 1
                note_y = ay + 30000 + label_h + role_h
                shapes.append(
                    text_box(
                        sid,
                        f"vf-actor-note-{a['id']}",
                        ax + 50000,
                        note_y,
                        aw - 100000,
                        ah - (note_y - ay) - 30000,
                        note,
                        size_pt=8,
                        color=sub_color,
                        font=ctx.font,
                        align="ctr",
                        auto_fit=True,
                    )
                )
                sid += 1
            elif role:
                shapes.append(
                    text_box(
                        sid,
                        f"vf-actor-lbl-{a['id']}",
                        ax + 40000,
                        ay + ah // 6,
                        aw - 80000,
                        ah // 2,
                        a["label"],
                        size_pt=14,
                        bold=True,
                        color=text_color,
                        font=ctx.font,
                        align="ctr",
                    )
                )
                sid += 1
                shapes.append(
                    text_box(
                        sid,
                        f"vf-actor-role-{a['id']}",
                        ax + 40000,
                        ay + ah * 3 // 5,
                        aw - 80000,
                        ah // 3,
                        str(role),
                        size_pt=9,
                        color=sub_color,
                        font=ctx.font,
                        align="ctr",
                    )
                )
                sid += 1
            else:
                shapes.append(
                    text_box(
                        sid,
                        f"vf-actor-lbl-{a['id']}",
                        ax + 40000,
                        ay + 40000,
                        aw - 80000,
                        ah - 80000,
                        a["label"],
                        size_pt=14,
                        bold=True,
                        color=text_color,
                        font=ctx.font,
                        align="ctr",
                        auto_fit=True,
                    )
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
