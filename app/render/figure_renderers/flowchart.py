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
        "Layered vertical flowchart (2-7 layers, up to 4 nodes per layer). "
        "Node kinds: start/end (rounded), process (rect), decision (diamond), "
        "data (parallelogram). "
        "content: {layers: [[{id, label, kind?}]], edges: [{from, to, label?}]}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "layers": [
            [{"id": "s", "label": "開始", "kind": "start"}],
            [{"id": "p1", "label": "申請内容を入力", "kind": "process"}],
            [{"id": "d1", "label": "金額 > 100万?", "kind": "decision"}],
            [
                {"id": "p2", "label": "上長承認", "kind": "process"},
                {"id": "p3", "label": "自動承認", "kind": "process"},
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

        n_layers = len(layers)
        margin_x = container.w // 50
        margin_y = container.h // 40

        plot_x = container.x + margin_x
        plot_y = container.y + margin_y
        plot_w = container.w - 2 * margin_x
        plot_h = container.h - 2 * margin_y

        layer_h = plot_h // n_layers
        # Looser node sizing: shorter cards leave room for breathing space
        # between layers and for the arrows to be visually obvious.
        node_h = max(_i(layer_h * 0.50), 280000)
        node_v_pad = (layer_h - node_h) // 2

        accent_w = max(_i(0.05 * 914400), 36000)  # ~3pt left bar.

        centers: dict[str, tuple[int, int]] = {}
        bboxes: dict[str, tuple[int, int, int, int]] = {}

        shapes: list[str] = []
        sid = ctx.next_shape_id

        for li, layer in enumerate(layers):
            n = len(layer)
            slot_w = plot_w // n
            node_w = max(_i(slot_w * 0.88), 700000)
            for ni, node in enumerate(layer):
                kind = node.get("kind", "process")
                slot_x = plot_x + ni * slot_w + (slot_w - node_w) // 2
                node_y = plot_y + li * layer_h + node_v_pad

                # Diamond keeps its own (wider) bounding box so its
                # inscribed text rectangle has room.
                if kind == "decision":
                    diamond_w = min(node_w, _i(node_h * 1.7))
                    slot_x += (node_w - diamond_w) // 2
                    used_w = diamond_w
                else:
                    used_w = node_w

                # Per-kind palette. Process/data lean white-on-purple
                # accent, start/end are the brand color, decision is
                # amber to call attention to the branch.
                if kind in ("start", "end"):
                    fill = p.purple_dk
                    text_color = "FFFFFF"
                    accent_color = None  # the body itself is the accent
                elif kind == "decision":
                    fill = "FFF6E6"  # warm white tint
                    text_color = p.black
                    accent_color = p.amber
                elif kind == "data":
                    fill = "F4F2FA"
                    text_color = p.black
                    accent_color = p.purple_lt
                else:  # process
                    fill = "FFFFFF"
                    text_color = p.black
                    accent_color = p.purple_dk

                if kind in ("start", "end"):
                    shapes.append(
                        round_rect_shape(
                            sid,
                            f"fc-{node['id']}",
                            slot_x,
                            node_y,
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
                            node_y,
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
                            node_y,
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
                            node_y,
                            used_w,
                            node_h,
                            fill,
                            corner_radius_pct=10,
                            shadow=True,
                        )
                    )
                    sid += 1
                    if accent_color is not None:
                        # Thin colored bar on the leftmost edge.
                        # Drawn as plain rect (no rounding) so it tucks
                        # behind the card's rounded corners visually.
                        shapes.append(
                            rect_shape(
                                sid,
                                f"fc-acc-{node['id']}",
                                slot_x,
                                node_y,
                                accent_w,
                                node_h,
                                accent_color,
                            )
                        )
                        sid += 1

                # Label centered with a healthy inset so JP text
                # doesn't kiss the rounded corners.
                if kind == "decision":
                    text_x = slot_x + used_w // 6
                    text_w = used_w * 2 // 3
                else:
                    text_x = slot_x + accent_w + 100000
                    text_w = used_w - accent_w - 200000
                shapes.append(
                    text_box(
                        sid,
                        f"fc-lbl-{node['id']}",
                        text_x,
                        node_y + 40000,
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

                centers[node["id"]] = (slot_x + used_w // 2, node_y + node_h // 2)
                bboxes[node["id"]] = (slot_x, node_y, used_w, node_h)

        for ei, e in enumerate(edges):
            src, dst = e["from"], e["to"]
            if src not in centers or dst not in centers:
                continue
            sx, sy, sw, sh = bboxes[src]
            dx, dy, dw, dh = bboxes[dst]
            sx_c = sx + sw // 2
            dx_c = dx + dw // 2
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
                # Edge labels sit on a tiny white pill so they don't
                # collide with the connector underneath.
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
