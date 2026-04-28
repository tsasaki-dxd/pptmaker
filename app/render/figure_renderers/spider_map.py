"""Spider / mind map: central concept + radial branches.

One central node and 3-8 branches arranged at evenly-spaced angles
starting from the top (12 o'clock) and going clockwise. Each branch
is a self-contained card that holds the branch label plus an
optional bullet list of sub-items, connected to the center by a
line.

Used for "DX 推進" / "顧客提供価値" / "プロジェクトのリスク" — radial
relationships where the center is the topic and each branch is a
peer-level facet (no implied flow direction)."""

from __future__ import annotations

import math
from typing import Any, ClassVar

from ..shapes import (
    TextParagraph,
    TextRun,
    _i,
    _xml_escape,
    round_rect_shape,
    text_box,
    text_box_paragraphs,
)
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MIN_BRANCHES = 3
_MAX_BRANCHES = 8
_MAX_ITEMS_PER_BRANCH = 4


def _ellipse(
    sp_id: int,
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    fill: str,
    line_color: str | None = None,
) -> str:
    ln = ""
    if line_color:
        ln = (
            f'<a:ln w="6350">'
            f'<a:solidFill><a:srgbClr val="{line_color}"/></a:solidFill>'
            f"</a:ln>"
        )
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f"<p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="ellipse"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
        f"{ln}"
        f"</p:spPr>"
        f'<p:txBody><a:bodyPr wrap="square" anchor="ctr"/><a:lstStyle/><a:p/></p:txBody>'
        f"</p:sp>"
    )


def _line(
    sp_id: int,
    name: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: str,
    width_emu: int = 9525,
) -> str:
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
        f"</a:ln>"
        f"</p:spPr>"
        f"</p:cxnSp>"
    )


@register
class SpiderMapRenderer(FigureRenderer):
    """Central concept + 3-8 radial branches with optional sub-items."""

    figure_type = "spider_map"
    description = (
        "Spider / mind map: one central topic with 3-8 radial branches; "
        "each branch may carry up to 4 sub-items. "
        "content: {center: {label}, branches: [{label, items?: [str, ...]}]}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "center": {"label": "DX 推進"},
        "branches": [
            {"label": "業務効率化", "items": ["RPA", "ノーコード"]},
            {"label": "データ活用", "items": ["BI", "AI 予測"]},
            {"label": "顧客体験", "items": ["UX 改善", "パーソナライズ"]},
            {"label": "人材育成", "items": ["教育", "リスキリング"]},
        ],
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        center = content.get("center")
        if not isinstance(center, dict) or not center.get("label"):
            errors.append("center.label required")
        branches = content.get("branches")
        if not isinstance(branches, list) or not (
            _MIN_BRANCHES <= len(branches) <= _MAX_BRANCHES
        ):
            errors.append(
                f"branches must be list of length {_MIN_BRANCHES}-{_MAX_BRANCHES}"
            )
        else:
            for bi, b in enumerate(branches):
                if not isinstance(b, dict) or not b.get("label"):
                    errors.append(f"branches[{bi}].label required")
                    continue
                items = b.get("items")
                if items is not None:
                    if not isinstance(items, list):
                        errors.append(f"branches[{bi}].items must be list")
                    elif len(items) > _MAX_ITEMS_PER_BRANCH:
                        errors.append(
                            f"branches[{bi}].items must have <= "
                            f"{_MAX_ITEMS_PER_BRANCH} entries"
                        )
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        center: dict[str, Any] = content["center"]
        branches: list[dict[str, Any]] = list(content["branches"])
        n = len(branches)

        # Geometry. Each branch is a self-contained roundRect card
        # carrying both label and items, so we don't have to chase
        # overflowing item lists with a separate text box. The card
        # height grows with the item count; the radius is sized so
        # cards don't crash into the center bubble or each other.
        canvas_min = min(container.w, container.h)
        cx = container.x + container.w // 2
        cy = container.y + container.h // 2

        center_w = _i(canvas_min * 0.28)
        center_h = _i(center_w * 0.55)

        # Pre-compute branch card heights so we can pick a radius that
        # at least clears the central bubble plus the tallest card.
        # Generous header and per-item heights so JP text + bullets
        # don't overlap when LibreOffice rasterizes the slide.
        max_items = max((len(b.get("items") or []) for b in branches), default=0)
        card_w = _i(canvas_min * 0.34)
        card_header_h = _i(canvas_min * 0.13)
        card_item_h = _i(canvas_min * 0.08)
        card_pad_v = _i(canvas_min * 0.04)
        card_h_base = card_header_h + max_items * card_item_h + card_pad_v

        # Radius from canvas center to branch *center*. Cap so cards
        # don't overflow the container; ensure they clear the central
        # bubble plus a small gap.
        max_radius_x = (container.w // 2) - card_w // 2 - _i(canvas_min * 0.02)
        max_radius_y = (container.h // 2) - card_h_base // 2 - _i(canvas_min * 0.02)
        min_radius = max(center_w, center_h) // 2 + _i(canvas_min * 0.08)
        radius = min(max(max_radius_x, max_radius_y, min_radius), max(max_radius_x, max_radius_y))
        radius = max(radius, min_radius)

        shapes: list[str] = []
        sid = ctx.next_shape_id

        # Branches first so connecting lines paint under the center bubble.
        for i, branch in enumerate(branches):
            angle_deg = -90 + (360.0 * i / n)
            rad = math.radians(angle_deg)
            bcx = cx + int(radius * math.cos(rad))
            bcy = cy + int(radius * math.sin(rad))

            items = branch.get("items") or []
            card_h = card_header_h + len(items) * card_item_h + card_pad_v
            bx = bcx - card_w // 2
            by = bcy - card_h // 2
            # Clamp to container so the card never bleeds off-canvas.
            bx = max(container.x, min(bx, container.x + container.w - card_w))
            by = max(container.y, min(by, container.y + container.h - card_h))

            # Connector center → card center. Drawn before the card so
            # the line tucks under the rounded edge.
            shapes.append(
                _line(
                    sid,
                    f"sm-line-{i}",
                    cx,
                    cy,
                    bx + card_w // 2,
                    by + card_h // 2,
                    p.purple_lt,
                    width_emu=12700,
                )
            )
            sid += 1

            shapes.append(
                round_rect_shape(
                    sid,
                    f"sm-card-{i}",
                    bx,
                    by,
                    card_w,
                    card_h,
                    p.purple_bg,
                    corner_radius_pct=18,
                    line_color=p.purple,
                    line_width_emu=6350,
                )
            )
            sid += 1

            # Header label — centered in the dedicated header band.
            shapes.append(
                text_box(
                    sid,
                    f"sm-card-lbl-{i}",
                    bx + 40000,
                    by + 20000,
                    card_w - 80000,
                    card_header_h - 40000,
                    branch["label"],
                    size_pt=11,
                    bold=True,
                    color=p.purple_dk,
                    font=ctx.font,
                    align="ctr",
                )
            )
            sid += 1

            if items:
                paragraphs = [
                    TextParagraph(
                        runs=(
                            TextRun(
                                text="・ " + str(it),
                                size_pt=8,
                                color=p.dark,
                            ),
                        ),
                        align="l",
                    )
                    for it in items
                ]
                items_y = by + card_header_h
                items_h = len(items) * card_item_h
                shapes.append(
                    text_box_paragraphs(
                        sid,
                        f"sm-card-items-{i}",
                        bx + 60000,
                        items_y,
                        card_w - 120000,
                        items_h,
                        paragraphs,
                        font=ctx.font,
                        anchor="t",
                        auto_fit=True,
                    )
                )
                sid += 1

        # Center bubble (drawn last so it sits on top of any radii).
        shapes.append(
            _ellipse(
                sid,
                "sm-center",
                cx - center_w // 2,
                cy - center_h // 2,
                center_w,
                center_h,
                p.purple,
            )
        )
        sid += 1
        shapes.append(
            text_box(
                sid,
                "sm-center-lbl",
                cx - center_w // 2 + 40000,
                cy - center_h // 2 + 40000,
                center_w - 80000,
                center_h - 80000,
                center["label"],
                size_pt=12,
                bold=True,
                color="FFFFFF",
                font=ctx.font,
                align="ctr",
                auto_fit=True,
            )
        )
        sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
