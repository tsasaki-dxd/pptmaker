"""Vertical flowchart with shape-coded nodes (start/process/decision/end) and arrow connectors.

Nodes are organized into ordered ``layers``; each layer is one
horizontal row, and layers stack top-to-bottom. ``edges`` are
arbitrary directed connections between node IDs and may carry a
short label (e.g. "Yes"/"No" out of a decision).

Auto-routing arbitrary 2D graphs is intentionally out of scope —
forcing layered input lets the renderer produce predictable output
without depending on a graph-layout library inside the Lambda
bundle. The LLM is responsible for picking the layer assignment.

Visual: flat cards with subtle drop shadow + colored left accent
bar coding the kind. Avoids the heavy purple borders of the first
pass — modern slides read better with whitespace and one accent
color per element instead of a frame around everything.
"""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import _i, _xml_escape, rect_shape, round_rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MIN_LAYERS = 2
_MAX_LAYERS = 7
_MAX_NODES_PER_LAYER = 4
_NODE_KINDS = {"start", "end", "process", "decision", "data"}

# Comfortable baseline node sizes — fit a 5-8 JP-char label plus a
# 1-2 line note at default font sizes without auto_fit having to
# kick in. Render uses min(baseline, available) so sparse charts
# don't oversize and crowded charts shrink gracefully.
_IDEAL_NODE_W = 1_550_000
_IDEAL_NODE_H = 720_000
# Floor so even a 7-layer by 4-parallel flow stays legible after
# auto_fit pulls text size down.
_MIN_NODE_W = 600_000
_MIN_NODE_H = 280_000


def _diamond(
    sp_id: int,
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    fill: str,
    *,
    shadow: bool = True,
) -> str:
    effect = ""
    if shadow:
        effect = (
            "<a:effectLst>"
            '<a:outerShdw blurRad="50800" dist="25400" dir="5400000" '
            'algn="t" rotWithShape="0">'
            '<a:srgbClr val="000000"><a:alpha val="14000"/></a:srgbClr>'
            "</a:outerShdw>"
            "</a:effectLst>"
        )
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f'<p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="diamond"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
        f'<a:ln><a:noFill/></a:ln>'
        f"{effect}"
        f"</p:spPr>"
        f'<p:txBody><a:bodyPr wrap="square" anchor="ctr"/><a:lstStyle/><a:p/></p:txBody>'
        f"</p:sp>"
    )


def _parallelogram(
    sp_id: int,
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    fill: str,
) -> str:
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f'<p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="parallelogram"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
        f'<a:ln><a:noFill/></a:ln>'
        "<a:effectLst>"
        '<a:outerShdw blurRad="50800" dist="25400" dir="5400000" '
        'algn="t" rotWithShape="0">'
        '<a:srgbClr val="000000"><a:alpha val="14000"/></a:srgbClr>'
        "</a:outerShdw>"
        "</a:effectLst>"
        f"</p:spPr>"
        f'<p:txBody><a:bodyPr wrap="square" anchor="ctr"/><a:lstStyle/><a:p/></p:txBody>'
        f"</p:sp>"
    )


def _arrow(
    sp_id: int,
    name: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: str,
    width_emu: int = 9525,
) -> str:
    """Connector with a triangle tail-end (arrow head at (x2, y2))."""
    bx, by = min(x1, x2), min(y1, y2)
    bw, bh = max(abs(x2 - x1), 1), max(abs(y2 - y1), 1)
    flip_h = "1" if x2 < x1 else "0"
    flip_v = "1" if y2 < y1 else "0"
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
        f'<a:tailEnd type="triangle" w="sm" len="sm"/>'
        f"</a:ln>"
        f"</p:spPr>"
        f"</p:cxnSp>"
    )


@register
class FlowchartRenderer(FigureRenderer):
    """Layered vertical flowchart with shape-coded nodes and arrows."""

    figure_type = "flowchart"
    description = (
        "Layered flowchart (2-7 layers, up to 4 nodes per layer). "
        "`direction` is `horizontal` by default (layers stretch left-to-right, "
        "nodes within a layer stack vertically) — fits the wide slide body "
        "better than `vertical` (set explicitly when the deck demands it). "
        "Node kinds: start/end (rounded), process (rect), decision (diamond), "
        "data (parallelogram). Each non-decision node accepts an optional "
        "1-2 line `note` rendered in muted text below the label (responsible "
        "team / SLA / output, etc.); decision nodes ignore note because the "
        "diamond's inscribed area is too narrow. "
        "content: {direction?: 'horizontal'|'vertical', "
        "layers: [[{id, label, kind?, note?}]], "
        "edges: [{from, to, label?}]}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "layers": [
            [{"id": "s", "label": "開始", "kind": "start"}],
            [
                {
                    "id": "p1",
                    "label": "申請内容を入力",
                    "kind": "process",
                    "note": "申請者 / 5分以内",
                }
            ],
            [{"id": "d1", "label": "金額 > 100万?", "kind": "decision"}],
            [
                {
                    "id": "p2",
                    "label": "上長承認",
                    "kind": "process",
                    "note": "1営業日 SLA",
                },
                {
                    "id": "p3",
                    "label": "自動承認",
                    "kind": "process",
                    "note": "ルールベース即時",
                },
            ],
            [{"id": "e", "label": "完了", "kind": "end"}],
        ],
        "edges": [
            {"from": "s", "to": "p1"},
            {"from": "p1", "to": "d1"},
            {"from": "d1", "to": "p2", "label": "Yes"},
            {"from": "d1", "to": "p3", "label": "No"},
            {"from": "p2", "to": "e"},
            {"from": "p3", "to": "e"},
        ],
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        layers = content.get("layers")
        if not isinstance(layers, list) or not (_MIN_LAYERS <= len(layers) <= _MAX_LAYERS):
            return ValidationResult(
                False, (f"layers must be list of length {_MIN_LAYERS}-{_MAX_LAYERS}",)
            )
        ids: set[str] = set()
        for li, layer in enumerate(layers):
            if not isinstance(layer, list) or not (1 <= len(layer) <= _MAX_NODES_PER_LAYER):
                errors.append(
                    f"layers[{li}] must be list of 1-{_MAX_NODES_PER_LAYER} nodes"
                )
                continue
            for ni, node in enumerate(layer):
                if not isinstance(node, dict):
                    errors.append(f"layers[{li}][{ni}] must be object")
                    continue
                nid = node.get("id")
                if not isinstance(nid, str) or not nid:
                    errors.append(f"layers[{li}][{ni}].id required")
                    continue
                if not node.get("label"):
                    errors.append(f"layers[{li}][{ni}].label required")
                kind = node.get("kind", "process")
                if kind not in _NODE_KINDS:
                    errors.append(
                        f"layers[{li}][{ni}].kind must be one of {sorted(_NODE_KINDS)}"
                    )
                ids.add(nid)

        edges = content.get("edges", [])
        if not isinstance(edges, list):
            errors.append("edges must be a list (may be empty)")
        else:
            for ei, e in enumerate(edges):
                if not isinstance(e, dict):
                    errors.append(f"edges[{ei}] must be object")
                    continue
                src, dst = e.get("from"), e.get("to")
                if src not in ids:
                    errors.append(f"edges[{ei}].from {src!r} not in layers")
                if dst not in ids:
                    errors.append(f"edges[{ei}].to {dst!r} not in layers")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        layers: list[list[dict[str, Any]]] = list(content["layers"])
        edges: list[dict[str, Any]] = list(content.get("edges") or [])
        # Default to horizontal because the slide body is wide and short
        # (about 8.4M wide by 2.8M tall in EMU). Vertical 5-layer flow
        # squeezes each row to ~0.5 inch which can't carry a label
        # plus a note. Caller can opt back into vertical via
        # `direction: "vertical"` if the deck layout demands it.
        direction = str(content.get("direction") or "horizontal").lower()
        horizontal = direction != "vertical"

        n_layers = len(layers)
        margin_x = container.w // 50
        margin_y = container.h // 40

        plot_x = container.x + margin_x
        plot_y = container.y + margin_y
        plot_w = container.w - 2 * margin_x
        plot_h = container.h - 2 * margin_y

        any_note = any(
            isinstance(n, dict)
            and isinstance(n.get("note"), str)
            and n["note"].strip()
            and n.get("kind", "process") != "decision"
            for layer in layers
            for n in layer
        )

        # Layer advance along the flow direction.
        layer_advance = (plot_w if horizontal else plot_h) // n_layers

        accent_w = max(_i(0.05 * 914400), 36000)  # ~3pt left bar.

        centers: dict[str, tuple[int, int]] = {}
        bboxes: dict[str, tuple[int, int, int, int]] = {}

        shapes: list[str] = []
        sid = ctx.next_shape_id

        for li, layer in enumerate(layers):
            n = len(layer)
            # Take min(baseline, available) so each node fits its slot
            # but never exceeds the ideal size — and floor it so the
            # text auto_fit has something readable to work with even
            # at maximum density (7 layers by 4 nodes).
            if horizontal:
                slot_cross = plot_h // n
                # Available room inside the slot. Use 88% so the
                # arrows have visible spacing even at low density.
                avail_w = max(_i(layer_advance * 0.88), _MIN_NODE_W)
                avail_h = max(_i(slot_cross * 0.88), _MIN_NODE_H)
                node_w = min(_IDEAL_NODE_W, avail_w)
                ideal_h = _IDEAL_NODE_H if any_note else int(_IDEAL_NODE_H * 0.7)
                node_h = min(ideal_h, avail_h)
                slot_v_pad = (slot_cross - node_h) // 2
            else:
                slot_cross = plot_w // n
                avail_w = max(_i(slot_cross * 0.88), _MIN_NODE_W)
                avail_h = max(_i(layer_advance * 0.88), _MIN_NODE_H)
                node_w = min(_IDEAL_NODE_W, avail_w)
                ideal_h = _IDEAL_NODE_H if any_note else int(_IDEAL_NODE_H * 0.7)
                node_h = min(ideal_h, avail_h)
                slot_v_pad = (layer_advance - node_h) // 2

            for ni, node in enumerate(layer):
                kind = node.get("kind", "process")

                if horizontal:
                    slot_x = plot_x + li * layer_advance + (layer_advance - node_w) // 2
                    slot_y = plot_y + ni * slot_cross + slot_v_pad
                else:
                    slot_x = plot_x + ni * slot_cross + (slot_cross - node_w) // 2
                    slot_y = plot_y + li * layer_advance + slot_v_pad

                if kind == "decision":
                    diamond_w = min(node_w, _i(node_h * 1.7))
                    slot_x += (node_w - diamond_w) // 2
                    used_w = diamond_w
                else:
                    used_w = node_w

                if kind in ("start", "end"):
                    fill = p.purple_dk
                    text_color = "FFFFFF"
                    accent_color = None
                elif kind == "decision":
                    fill = "FFF6E6"
                    text_color = p.black
                    accent_color = p.amber
                elif kind == "data":
                    fill = "F4F2FA"
                    text_color = p.black
                    accent_color = p.purple_lt
                else:
                    fill = "FFFFFF"
                    text_color = p.black
                    accent_color = p.purple_dk

                if kind in ("start", "end"):
                    shapes.append(
                        round_rect_shape(
                            sid,
                            f"fc-{node['id']}",
                            slot_x,
                            slot_y,
                            used_w,
                            node_h,
                            fill,
                            corner_radius_pct=50,
                            shadow=True,
                        )
                    )
                    sid += 1
                elif kind == "decision":
                    shapes.append(
                        _diamond(
                            sid,
                            f"fc-{node['id']}",
                            slot_x,
                            slot_y,
                            used_w,
                            node_h,
                            fill,
                            shadow=True,
                        )
                    )
                    sid += 1
                elif kind == "data":
                    shapes.append(
                        _parallelogram(
                            sid,
                            f"fc-{node['id']}",
                            slot_x,
                            slot_y,
                            used_w,
                            node_h,
                            fill,
                        )
                    )
                    sid += 1
                else:
                    shapes.append(
                        round_rect_shape(
                            sid,
                            f"fc-{node['id']}",
                            slot_x,
                            slot_y,
                            used_w,
                            node_h,
                            fill,
                            corner_radius_pct=10,
                            shadow=True,
                        )
                    )
                    sid += 1
                    if accent_color is not None:
                        shapes.append(
                            rect_shape(
                                sid,
                                f"fc-acc-{node['id']}",
                                slot_x,
                                slot_y,
                                accent_w,
                                node_h,
                                accent_color,
                            )
                        )
                        sid += 1

                if kind == "decision":
                    text_x = slot_x + used_w // 6
                    text_w = used_w * 2 // 3
                else:
                    text_x = slot_x + accent_w + 100000
                    text_w = used_w - accent_w - 200000

                note_raw = node.get("note") if kind != "decision" else None
                note = (
                    note_raw.strip()
                    if isinstance(note_raw, str) and note_raw.strip()
                    else ""
                )
                if note:
                    label_h = _i(node_h * 0.45)
                    note_y = slot_y + label_h
                    note_h = node_h - label_h - 40000
                    shapes.append(
                        text_box(
                            sid,
                            f"fc-lbl-{node['id']}",
                            text_x,
                            slot_y + 30000,
                            text_w,
                            label_h - 30000,
                            node["label"],
                            size_pt=11,
                            bold=kind in ("start", "end"),
                            color=text_color,
                            font=ctx.font,
                            align="ctr",
                            auto_fit=True,
                        )
                    )
                    sid += 1
                    note_color = "FFFFFF" if kind in ("start", "end") else p.muted
                    shapes.append(
                        text_box(
                            sid,
                            f"fc-note-{node['id']}",
                            text_x,
                            note_y,
                            text_w,
                            note_h,
                            note,
                            size_pt=8,
                            color=note_color,
                            font=ctx.font,
                            align="ctr",
                            auto_fit=True,
                        )
                    )
                else:
                    shapes.append(
                        text_box(
                            sid,
                            f"fc-lbl-{node['id']}",
                            text_x,
                            slot_y + 40000,
                            text_w,
                            node_h - 80000,
                            node["label"],
                            size_pt=11,
                            bold=kind in ("start", "end", "decision"),
                            color=text_color,
                            font=ctx.font,
                            align="ctr",
                            auto_fit=True,
                        )
                    )
                sid += 1

                centers[node["id"]] = (slot_x + used_w // 2, slot_y + node_h // 2)
                bboxes[node["id"]] = (slot_x, slot_y, used_w, node_h)

        for ei, e in enumerate(edges):
            src, dst = e["from"], e["to"]
            if src not in centers or dst not in centers:
                continue
            sx, sy, sw, sh = bboxes[src]
            dx, dy, dw, dh = bboxes[dst]
            sx_c = sx + sw // 2
            sy_c = sy + sh // 2
            dx_c = dx + dw // 2
            dy_c = dy + dh // 2

            if horizontal:
                if sx + sw <= dx:
                    # forward (left → right)
                    start = (sx + sw, sy_c)
                    end = (dx, dy_c)
                elif dx + dw <= sx:
                    # backward (right → left, e.g. retry loop)
                    start = (sx, sy_c)
                    end = (dx + dw, dy_c)
                else:
                    start = centers[src]
                    end = centers[dst]
            else:  # vertical
                if sy + sh <= dy:
                    start = (sx_c, sy + sh)
                    end = (dx_c, dy)
                elif dy + dh <= sy:
                    start = (sx_c, sy)
                    end = (dx_c, dy + dh)
                else:
                    start = centers[src]
                    end = centers[dst]

            shapes.append(
                _arrow(
                    sid,
                    f"fc-edge-{ei}",
                    start[0],
                    start[1],
                    end[0],
                    end[1],
                    p.muted,
                    width_emu=9525,
                )
            )
            sid += 1

            label = e.get("label")
            if label:
                mid_x = (start[0] + end[0]) // 2
                mid_y = (start[1] + end[1]) // 2
                lbl_w = 480000
                lbl_h = 220000
                shapes.append(
                    round_rect_shape(
                        sid,
                        f"fc-edge-pill-{ei}",
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
                        f"fc-edge-lbl-{ei}",
                        mid_x - lbl_w // 2,
                        mid_y - lbl_h // 2,
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

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
