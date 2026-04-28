"""Spider / mind map: central concept + radial branches.

One central node and 3-8 branches arranged at evenly-spaced angles
starting from the top (12 o'clock) and going clockwise. Each branch
is a self-contained card that holds the branch label plus an
optional bullet list of sub-items, connected to the center by a
line.

Used for "DX 推進" / "顧客提供価値" / "プロジェクトのリスク" — radial
relationships where the center is the topic and each branch is a
peer-level facet (no implied flow direction).

Visual: flat white branch cards with shadow + small color-coded
header bar; radial lines are thin and de-saturated. The center
bubble is the only saturated element so it reads as the anchor.
"""

from __future__ import annotations

import math
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

_MIN_BRANCHES = 3
_MAX_BRANCHES = 8
_MAX_ITEMS_PER_BRANCH = 4

# Cycle accent colors so adjacent branches don't share one.
_BRANCH_ACCENTS = ("purple_dk", "amber", "green", "purple_lt", "muted", "purple")


def _ellipse(
    sp_id: int,
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    fill: str,
    *,
    shadow: bool = False,
) -> str:
    effect = ""
    if shadow:
        effect = (
            "<a:effectLst>"
            '<a:outerShdw blurRad="76200" dist="38100" dir="5400000" '
            'algn="t" rotWithShape="0">'
            '<a:srgbClr val="000000"><a:alpha val="18000"/></a:srgbClr>'
            "</a:outerShdw>"
            "</a:effectLst>"
        )
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f"<p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="ellipse"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
        f'<a:ln><a:noFill/></a:ln>'
        f"{effect}"
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
    width_emu: int = 6350,
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

        canvas_min = min(container.w, container.h)
        cx = container.x + container.w // 2
        cy = container.y + container.h // 2

        # Center is a circle (square aspect) so it doesn't squash the
        # label awkwardly when the canvas is wide.
        center_d = _i(canvas_min * 0.26)

        # Branch card sizing — narrower cards so we can crank the
        # horizontal radius further on the wide content canvas
        # (8.4M wide by 2.8M tall EMU) without overlapping the center.
        max_items = max((len(b.get("items") or []) for b in branches), default=0)
        card_w = _i(canvas_min * 0.42)
        card_header_h = _i(canvas_min * 0.18)
        card_item_h = _i(canvas_min * 0.08)
        card_pad_v = _i(canvas_min * 0.04)
        card_h_base = card_header_h + max_items * card_item_h + card_pad_v

        # Elliptical placement matches the canvas aspect: branches at
        # left/right get pushed further out (where there's room),
        # top/bottom stay close-ish (where there isn't). Without this
        # the horizontal-pair branches collide with the center bubble.
        margin = _i(canvas_min * 0.02)
        radius_x = max((container.w // 2) - card_w // 2 - margin, center_d)
        radius_y = max((container.h // 2) - card_h_base // 2 - margin, center_d // 2)

        shapes: list[str] = []
        sid = ctx.next_shape_id

        # Branches first so connectors paint under the center bubble.
        for i, branch in enumerate(branches):
            angle_deg = -90 + (360.0 * i / n)
            rad = math.radians(angle_deg)
            bcx = cx + int(radius_x * math.cos(rad))
            bcy = cy + int(radius_y * math.sin(rad))

            items = branch.get("items") or []
            card_h = card_header_h + len(items) * card_item_h + card_pad_v
            bx = bcx - card_w // 2
            by = bcy - card_h // 2
            bx = max(container.x, min(bx, container.x + container.w - card_w))
            by = max(container.y, min(by, container.y + container.h - card_h))

            # Connector center → card center (drawn before card).
            shapes.append(
                _line(
                    sid,
                    f"sm-line-{i}",
                    cx,
                    cy,
                    bx + card_w // 2,
                    by + card_h // 2,
                    p.border,
                    width_emu=6350,
                )
            )
            sid += 1

            accent_attr = _BRANCH_ACCENTS[i % len(_BRANCH_ACCENTS)]
            accent_color = getattr(p, accent_attr, p.purple_dk)

            # Card body: white with shadow, no border.
            shapes.append(
                round_rect_shape(
                    sid,
                    f"sm-card-{i}",
                    bx,
                    by,
                    card_w,
                    card_h,
                    "FFFFFF",
                    corner_radius_pct=14,
                    shadow=True,
                )
            )
            sid += 1

            # Top accent bar (subtle).
            bar_h = max(_i(canvas_min * 0.012), 24000)
            shapes.append(
                rect_shape(
                    sid,
                    f"sm-card-bar-{i}",
                    bx + _i(card_w * 0.06),
                    by + _i(card_h * 0.10),
                    _i(card_w * 0.18),
                    bar_h,
                    accent_color,
                )
            )
            sid += 1

            # Header sits in the top band only — no part of the label
            # bleeds into the items area below.
            header_text_y = by + _i(card_header_h * 0.35)
            header_text_h = card_header_h - _i(card_header_h * 0.4)
            shapes.append(
                text_box(
                    sid,
                    f"sm-card-lbl-{i}",
                    bx + 60000,
                    header_text_y,
                    card_w - 120000,
                    header_text_h,
                    branch["label"],
                    size_pt=12,
                    bold=True,
                    color=p.black,
                    font=ctx.font,
                    align="l",
                )
            )
            sid += 1

            if items:
                paragraphs = [
                    TextParagraph(
                        runs=(
                            TextRun(
                                text="・ " + str(it),
                                size_pt=9,
                                color=p.dark,
                            ),
                        ),
                        align="l",
                        space_before_pt=2,
                    )
                    for it in items
                ]
                # Anchor the items block under the header row; the
                # `card_header_h` band reserves enough vertical space
                # for the label so items never crowd it.
                shapes.append(
                    text_box_paragraphs(
                        sid,
                        f"sm-card-items-{i}",
                        bx + 80000,
                        by + card_header_h,
                        card_w - 160000,
                        len(items) * card_item_h,
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
                cx - center_d // 2,
                cy - center_d // 2,
                center_d,
                center_d,
                p.purple_dk,
                shadow=True,
            )
        )
        sid += 1
        shapes.append(
            text_box(
                sid,
                "sm-center-lbl",
                cx - center_d // 2 + 60000,
                cy - center_d // 2 + 60000,
                center_d - 120000,
                center_d - 120000,
                center["label"],
                size_pt=14,
                bold=True,
                color="FFFFFF",
                font=ctx.font,
                align="ctr",
                auto_fit=True,
            )
        )
        sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
