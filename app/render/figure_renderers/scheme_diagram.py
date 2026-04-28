"""Project-finance / SPC-style scheme diagram.

Used for diagrams like an SPC (特別目的会社) scheme, GK-TK structure,
or any "central entity surrounded by typed contractual / cash /
asset flows with multiple stakeholder groups" picture. value_flow
solves the small (2-6 peer)商流 case; this renderer takes over once
you need 8-12+ stakeholders, fixed regions (financiers on the left,
business on the right, end-users at the bottom), and clean
L-shape routing.

Layout: actors are placed by `region` ∈ {left, right, center, top,
bottom}. The center actor is rendered larger and in the brand color
to read as the pivot of the scheme; flanking columns (left / right)
stack actors vertically, and top / bottom rows distribute actors
horizontally across the central area. Optional `groups` wrap a set
of region-mates with a labelled rounded background so clusters like
"投資家 (LP + GP)" or "事業会社 (Dev + Op)" read as one unit.

Connector default is `bent` (single right-angle / L-shape) because
the orthogonal routing matches the rectangular grid the regions
imply. Curves and straight lines remain available via
`connector_style`.
"""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import (
    _i,
    _xml_escape,
    rect_shape,
    round_rect_shape,
    text_box,
)
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MIN_ACTORS = 3
_MAX_ACTORS = 14
_MAX_GROUPS = 4
_MAX_PER_COLUMN = 6
_MAX_PER_ROW = 4
_FLOW_KINDS = ("money", "goods", "info", "contract")
_REGIONS = ("left", "right", "center", "top", "bottom")
_CONNECTOR_STYLES = ("straight", "curved", "bent")
_PRST_BY_STYLE = {
    "straight": "line",
    "bent": "bentConnector3",
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
    style: str = "bent",
) -> str:
    bx, by = min(x1, x2), min(y1, y2)
    bw, bh = max(abs(x2 - x1), 1), max(abs(y2 - y1), 1)
    flip_h = "1" if x2 < x1 else "0"
    flip_v = "1" if y2 < y1 else "0"
    prst = _PRST_BY_STYLE.get(style, "bentConnector3")
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
    """Where the line from (cx, cy) toward (ax, ay) hits the rect perimeter."""
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
class SchemeDiagramRenderer(FigureRenderer):
    """Project-finance / SPC scheme: regions × groups × typed flows."""

    figure_type = "scheme_diagram"
    description = (
        "Project-finance / SPC-style scheme diagram. Use for SPC / "
        "GK-TK / TMK / プロジェクトファイナンス / M&A スキーム where "
        "a central entity is surrounded by typed contractual / cash / "
        "asset flows with 8-14 stakeholders. "
        "Each actor declares its `region`: 'center' (the pivot — usually "
        "SPC / TMK / 受け皿会社, mark as primary=true), 'left' (typically "
        "financiers / investors / lenders stacked vertically), 'right' "
        "(business / operations stakeholders stacked vertically), 'top' "
        "(regulators / parent entities, distributed horizontally), or "
        "'bottom' (end users / customers, distributed horizontally). "
        "Optional `groups` wrap region-mates in a labelled background "
        "(e.g. '投資家' covering LP + GP). Flows carry a kind (money / "
        "goods / info / contract → amber / purple / muted / green). "
        "`connector_style` defaults to 'bent' for clean orthogonal "
        "L-routes; 'curved' / 'straight' also available. "
        "content: {actors: [{id, label, region, primary?, sub?, note?}], "
        "groups?: [{name, members: [id, ...], accent?}], "
        "flows: [{from, to, label?, kind?}], "
        "connector_style?: 'straight'|'curved'|'bent'}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "actors": [
            {
                "id": "spc",
                "label": "SPC",
                "region": "center",
                "primary": True,
                "sub": "特別目的会社",
            },
            {"id": "bank", "label": "金融機関", "region": "left"},
            {"id": "lp", "label": "投資家 LP", "region": "left"},
            {"id": "gp", "label": "投資家 GP", "region": "left"},
            {"id": "dev", "label": "デベロッパー", "region": "right"},
            {"id": "op", "label": "運営会社", "region": "right"},
            {"id": "user", "label": "エンドユーザー", "region": "bottom"},
        ],
        "groups": [
            {"name": "投資家", "members": ["lp", "gp"], "accent": "purple"},
        ],
        "flows": [
            {"from": "bank", "to": "spc", "label": "融資", "kind": "contract"},
            {"from": "spc", "to": "bank", "label": "返済", "kind": "money"},
            {"from": "lp", "to": "spc", "label": "出資", "kind": "money"},
            {"from": "spc", "to": "lp", "label": "配当", "kind": "money"},
            {"from": "gp", "to": "spc", "label": "出資 / 運営", "kind": "money"},
            {"from": "dev", "to": "spc", "label": "売買契約", "kind": "contract"},
            {"from": "spc", "to": "op", "label": "運営委託", "kind": "contract"},
            {"from": "user", "to": "op", "label": "対価", "kind": "money"},
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
        regions_seen: dict[str, int] = {r: 0 for r in _REGIONS}
        for i, a in enumerate(actors):
            if not isinstance(a, dict):
                errors.append(f"actors[{i}] must be object")
                continue
            aid = a.get("id")
            if not isinstance(aid, str) or not aid:
                errors.append(f"actors[{i}].id required")
                continue
            if aid in ids:
                errors.append(f"duplicate actor id: {aid}")
            ids.add(aid)
            if not a.get("label"):
                errors.append(f"actors[{i}].label required")
            region = a.get("region")
            if region not in _REGIONS:
                errors.append(
                    f"actors[{i}].region must be one of {list(_REGIONS)}"
                )
                continue
            regions_seen[region] += 1

        if regions_seen["center"] > 1:
            errors.append("at most one actor can be in region='center'")
        if regions_seen["left"] > _MAX_PER_COLUMN:
            errors.append(f"region='left' supports up to {_MAX_PER_COLUMN}")
        if regions_seen["right"] > _MAX_PER_COLUMN:
            errors.append(f"region='right' supports up to {_MAX_PER_COLUMN}")
        if regions_seen["top"] > _MAX_PER_ROW:
            errors.append(f"region='top' supports up to {_MAX_PER_ROW}")
        if regions_seen["bottom"] > _MAX_PER_ROW:
            errors.append(f"region='bottom' supports up to {_MAX_PER_ROW}")

        groups = content.get("groups", [])
        if groups is not None:
            if not isinstance(groups, list) or len(groups) > _MAX_GROUPS:
                errors.append(f"groups must be list of <= {_MAX_GROUPS}")
            else:
                for gi, g in enumerate(groups):
                    if not isinstance(g, dict) or not g.get("name"):
                        errors.append(f"groups[{gi}].name required")
                        continue
                    members = g.get("members")
                    if not isinstance(members, list) or not members:
                        errors.append(f"groups[{gi}].members must be non-empty list")
                        continue
                    for mi, m in enumerate(members):
                        if m not in ids:
                            errors.append(
                                f"groups[{gi}].members[{mi}]={m!r} not in actors"
                            )

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
        groups: list[dict[str, Any]] = list(content.get("groups") or [])
        flows: list[dict[str, Any]] = list(content.get("flows") or [])

        connector_style = str(content.get("connector_style") or "bent").lower()
        if connector_style not in _CONNECTOR_STYLES:
            connector_style = "bent"

        # Group actors by region.
        by_region: dict[str, list[dict[str, Any]]] = {r: [] for r in _REGIONS}
        for a in actors:
            by_region[a.get("region", "center")].append(a)

        canvas_w = container.w
        canvas_h = container.h

        # Region sizes — only reserve space for regions that have actors.
        col_w_pct = 0.24
        row_h_pct = 0.22
        left_w = _i(canvas_w * col_w_pct) if by_region["left"] else 0
        right_w = _i(canvas_w * col_w_pct) if by_region["right"] else 0
        top_h = _i(canvas_h * row_h_pct) if by_region["top"] else 0
        bottom_h = _i(canvas_h * row_h_pct) if by_region["bottom"] else 0

        center_x = container.x + left_w
        center_w = canvas_w - left_w - right_w
        center_y = container.y + top_h
        center_h = canvas_h - top_h - bottom_h

        positions: dict[str, tuple[int, int, int, int]] = {}

        # Lookup: actor_id → group index, for column reordering and
        # title-band reservation. -1 means ungrouped.
        member_to_group: dict[str, int] = {}
        for gi, g in enumerate(groups):
            for m in g.get("members", []):
                # Multiple groups claiming the same actor would be a
                # validation bug; the last one wins here without
                # special-casing.
                member_to_group[m] = gi

        # Title-band height reserved above each group's first member so
        # the group's labelled top bar doesn't crash into a non-member
        # actor positioned right above it.
        col_title_band = max(_i(canvas_h * 0.07), 200000)
        col_title_pad = max(_i(canvas_w * 0.014), 24000)
        title_room = col_title_band + col_title_pad

        # ---- left / right columns ------------------------------------
        def _layout_column(
            actor_list: list[dict[str, Any]], col_x: int, col_w: int
        ) -> None:
            if not actor_list:
                return
            # Reorder so ungrouped actors come first, then group
            # members clustered together (by group index, preserving
            # original order within each group via stable sort). The
            # group's title bar then has a clean strip of column to
            # render in without overlapping a non-member.
            ordered = sorted(
                actor_list,
                key=lambda a: member_to_group.get(a["id"], -1),
            )
            n = len(ordered)
            col_y = container.y
            col_h = canvas_h
            base_gap = max(_i(col_h / (n * 7)), 30000)

            # How many groups have at least one member in this column?
            # Each one needs one extra title-room slot inserted before
            # its first member.
            seen_groups: set[int] = set()
            extras = 0
            for a in ordered:
                gid = member_to_group.get(a["id"], -1)
                if gid >= 0 and gid not in seen_groups:
                    seen_groups.add(gid)
                    extras += 1

            avail = col_h - base_gap * (n + 1) - title_room * extras
            ah = max(avail // n, 240000)

            cur_y = col_y + base_gap
            placed_groups: set[int] = set()
            for a in ordered:
                gid = member_to_group.get(a["id"], -1)
                if gid >= 0 and gid not in placed_groups:
                    placed_groups.add(gid)
                    cur_y += title_room
                positions[a["id"]] = (col_x + 30000, cur_y, col_w - 60000, ah)
                cur_y += ah + base_gap

        _layout_column(by_region["left"], container.x, left_w)
        _layout_column(
            by_region["right"], container.x + canvas_w - right_w, right_w
        )

        # ---- top / bottom rows --------------------------------------
        def _layout_row(
            actor_list: list[dict[str, Any]], row_y: int, row_h: int
        ) -> None:
            if not actor_list:
                return
            n = len(actor_list)
            row_x = center_x
            row_w = center_w
            gap = max(row_w // (n * 8), 30000)
            avail = row_w - gap * (n + 1)
            aw = avail // n
            ah = row_h - 30000
            for i, a in enumerate(actor_list):
                ax = row_x + gap + i * (aw + gap)
                ay = row_y + 15000
                positions[a["id"]] = (ax, ay, aw, ah)

        _layout_row(by_region["top"], container.y, top_h)
        _layout_row(
            by_region["bottom"], container.y + canvas_h - bottom_h, bottom_h
        )

        # ---- center actor -------------------------------------------
        center_actors = by_region["center"]
        if center_actors:
            # Single actor expected — make it large and centered in
            # the central rectangle.
            a = center_actors[0]
            cw = _i(center_w * 0.55)
            ch = _i(center_h * 0.55)
            cx_off = center_x + (center_w - cw) // 2
            cy_off = center_y + (center_h - ch) // 2
            positions[a["id"]] = (cx_off, cy_off, cw, ch)

        sid = ctx.next_shape_id
        shapes: list[str] = []

        # ---- group containers (drawn first so they sit behind) -----
        for gi, g in enumerate(groups):
            members = [m for m in g["members"] if m in positions]
            if not members:
                continue
            xs = [positions[m][0] for m in members]
            ys = [positions[m][1] for m in members]
            xe = [positions[m][0] + positions[m][2] for m in members]
            ye = [positions[m][1] + positions[m][3] for m in members]
            pad = max(_i(canvas_w * 0.014), 24000)
            title_band = max(_i(canvas_h * 0.07), 200000)
            gx = min(xs) - pad
            gy = min(ys) - pad - title_band
            gw = max(xe) - gx + pad
            gh = max(ye) - gy + pad
            accent_name = (g.get("accent") or "purple_lt").strip().lower()
            accent_color = getattr(p, accent_name, p.purple_lt)
            # Background (very light tint).
            shapes.append(
                round_rect_shape(
                    sid,
                    f"sd-group-{gi}",
                    gx,
                    gy,
                    gw,
                    gh,
                    "FAF8FD",
                    corner_radius_pct=6,
                    line_color=p.border,
                    line_width_emu=6350,
                )
            )
            sid += 1
            # Title band.
            shapes.append(
                rect_shape(
                    sid,
                    f"sd-group-bar-{gi}",
                    gx,
                    gy,
                    gw,
                    title_band,
                    accent_color,
                )
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"sd-group-lbl-{gi}",
                    gx + 80000,
                    gy + 20000,
                    gw - 160000,
                    title_band - 40000,
                    g["name"],
                    size_pt=10,
                    bold=True,
                    color="FFFFFF",
                    font=ctx.font,
                    align="l",
                )
            )
            sid += 1

        # ---- connectors --------------------------------------------
        # Detect bidirectional pairs to offset.
        pair_count: dict[tuple[str, str], int] = {}
        for f in flows:
            key = tuple(sorted((f["from"], f["to"])))
            pair_count[key] = pair_count.get(key, 0) + 1
        pair_drawn: dict[tuple[str, str], int] = {}

        kind_color = {
            "money": p.amber,
            "goods": p.purple_dk,
            "info": p.muted,
            "contract": p.green,
        }

        offset_step = _i(min(canvas_w, canvas_h) * 0.025)

        for fi, f in enumerate(flows):
            src, dst = f["from"], f["to"]
            if src not in positions or dst not in positions:
                continue
            sx, sy, sw, sh = positions[src]
            dx, dy, dw, dh = positions[dst]
            scx, scy = sx + sw // 2, sy + sh // 2
            dcx, dcy = dx + dw // 2, dy + dh // 2
            start = _rect_edge_intersect(scx, scy, sw, sh, dcx, dcy)
            end = _rect_edge_intersect(dcx, dcy, dw, dh, scx, scy)

            pair_key = tuple(sorted((src, dst)))
            already = pair_drawn.get(pair_key, 0)
            pair_drawn[pair_key] = already + 1
            if pair_count[pair_key] >= 2:
                # Offset perpendicular to the line direction so the
                # two arrows of a bidirectional pair don't sit on top
                # of each other.
                vx = end[0] - start[0]
                vy = end[1] - start[1]
                length = (vx * vx + vy * vy) ** 0.5 or 1.0
                px = vy / length
                py = -vx / length
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
                    f"sd-flow-{fi}",
                    start[0],
                    start[1],
                    end[0],
                    end[1],
                    color,
                    width_emu=9525,
                    head_size="med",
                    style=connector_style,
                )
            )
            sid += 1
            label = f.get("label")
            if label:
                # Place label on a white pill at ~40% along the line
                # so adjacent labels don't all collapse onto the same
                # midpoint when flows fan out from the center.
                lx = start[0] + (end[0] - start[0]) * 40 // 100
                ly = start[1] + (end[1] - start[1]) * 40 // 100
                # Pill width grows with label length so JP labels like
                # "出資 / 運営" don't overflow the default. ~80k EMU
                # per character at 8pt JP plus padding.
                lbl_text = str(label)
                lbl_w = max(720000, 80000 * len(lbl_text) + 200000)
                lbl_h = 240000
                shapes.append(
                    round_rect_shape(
                        sid,
                        f"sd-flow-pill-{fi}",
                        lx - lbl_w // 2,
                        ly - lbl_h // 2,
                        lbl_w,
                        lbl_h,
                        "FFFFFF",
                        corner_radius_pct=50,
                        line_color=color,
                        line_width_emu=4763,
                    )
                )
                sid += 1
                shapes.append(
                    text_box(
                        sid,
                        f"sd-flow-lbl-{fi}",
                        lx - lbl_w // 2,
                        ly - lbl_h // 2,
                        lbl_w,
                        lbl_h,
                        lbl_text,
                        size_pt=8,
                        color=p.dark,
                        font=ctx.font,
                        auto_fit=True,
                        align="ctr",
                    )
                )
                sid += 1

        # ---- actor cards -------------------------------------------
        for a in actors:
            if a["id"] not in positions:
                continue
            ax, ay, aw, ah = positions[a["id"]]
            primary = bool(a.get("primary"))
            fill = p.purple_dk if primary else "FFFFFF"
            shapes.append(
                round_rect_shape(
                    sid,
                    f"sd-actor-{a['id']}",
                    ax,
                    ay,
                    aw,
                    ah,
                    fill,
                    corner_radius_pct=10,
                    shadow=True,
                )
            )
            sid += 1

            text_color = "FFFFFF" if primary else p.black
            sub_color = "FFFFFF" if primary else p.muted
            label = a["label"]
            sub = a.get("sub")
            note_raw = a.get("note")
            note = (
                note_raw.strip()
                if isinstance(note_raw, str) and note_raw.strip()
                else ""
            )
            label_size = 14 if primary else 11

            # Stacked vertical text: label / sub / note (any of the
            # last two optional). Use a fixed band per row so the
            # primary card's bigger label has room without colliding.
            rows: list[tuple[str, int, str]] = []  # (text, size_pt, color)
            rows.append((label, label_size, text_color))
            if sub:
                rows.append((str(sub), 9, sub_color))
            if note:
                rows.append((note, 8, sub_color))

            n_rows = len(rows)
            row_h = (ah - 40000) // max(n_rows, 1)
            for ri, (txt, size_pt, color) in enumerate(rows):
                shapes.append(
                    text_box(
                        sid,
                        f"sd-actor-{a['id']}-r{ri}",
                        ax + 40000,
                        ay + 20000 + ri * row_h,
                        aw - 80000,
                        row_h,
                        txt,
                        size_pt=size_pt,
                        bold=ri == 0,
                        color=color,
                        font=ctx.font,
                        align="ctr",
                        auto_fit=True,
                    )
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
