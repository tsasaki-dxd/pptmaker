"""Porter-style value chain.

Two stacked bands:

  * **support** activities (0-4 items): plain rectangles strung
    horizontally above the primary chain. Conventionally things like
    "技術開発" / "人事" / "経理".
  * **primary** activities (3-7 items): chevron-shaped boxes that
    interlock left-to-right. Think 調達 → 製造 → 物流 → 販売 → サービス.
  * Optional **margin_label** (e.g. "利益") gets a right-pointing
    triangle on the far right cap.

This is intentionally narrower than process_flow — process_flow is
"steps that follow each other", value chain is the specific
business-strategy layout where supporting functions sit above the
primary value chain.
"""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import _i, _xml_escape, rect_shape, round_rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MIN_PRIMARY = 3
_MAX_PRIMARY = 7
_MAX_SUPPORT = 4


def _chevron(
    sp_id: int,
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    fill: str,
    *,
    indent_pct: int = 50,
) -> str:
    """Right-pointing chevron (left side concave, right side convex).
    `indent_pct` 0..100 controls how deep the indent / point is."""
    indent = max(0, min(100, indent_pct))
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f'<p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="chevron">'
        f'<a:avLst><a:gd name="adj" fmla="val {indent * 1000}"/></a:avLst>'
        f'</a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
        f'<a:ln><a:noFill/></a:ln>'
        '<a:effectLst>'
        '<a:outerShdw blurRad="50800" dist="25400" dir="5400000" '
        'algn="t" rotWithShape="0">'
        '<a:srgbClr val="000000"><a:alpha val="14000"/></a:srgbClr>'
        '</a:outerShdw>'
        '</a:effectLst>'
        f"</p:spPr>"
        f'<p:txBody><a:bodyPr wrap="square" anchor="ctr"/><a:lstStyle/><a:p/></p:txBody>'
        f"</p:sp>"
    )


def _right_triangle(
    sp_id: int,
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    fill: str,
) -> str:
    """Right-pointing triangle for the margin cap."""
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f'<p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="rtTriangle"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
        f'<a:ln><a:noFill/></a:ln>'
        '<a:effectLst>'
        '<a:outerShdw blurRad="50800" dist="25400" dir="5400000" '
        'algn="t" rotWithShape="0">'
        '<a:srgbClr val="000000"><a:alpha val="14000"/></a:srgbClr>'
        '</a:outerShdw>'
        '</a:effectLst>'
        f"</p:spPr>"
        f'<p:txBody><a:bodyPr wrap="square" anchor="ctr"/><a:lstStyle/><a:p/></p:txBody>'
        f"</p:sp>"
    )


@register
class ValueChainRenderer(FigureRenderer):
    """Porter value chain — primary chevrons + optional support row + margin cap."""

    figure_type = "value_chain"
    description = (
        "Porter-style value chain. Primary activities (3-7) render as "
        "interlocking chevrons; optional support activities (0-4) sit as "
        "plain boxes above them; an optional margin_label adds a "
        "right-pointing triangle at the end. "
        "content: {primary: [str, ...], support?: [str, ...], margin_label?: str}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "primary": ["調達", "製造", "物流", "販売", "サービス"],
        "support": ["技術開発", "人事", "経理"],
        "margin_label": "利益",
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        primary = content.get("primary")
        if not isinstance(primary, list) or not (_MIN_PRIMARY <= len(primary) <= _MAX_PRIMARY):
            errors.append(
                f"primary must be list of length {_MIN_PRIMARY}-{_MAX_PRIMARY}"
            )
        else:
            for i, p in enumerate(primary):
                if not isinstance(p, str) or not p.strip():
                    errors.append(f"primary[{i}] must be non-empty string")
        support = content.get("support")
        if support is not None:
            if not isinstance(support, list) or len(support) > _MAX_SUPPORT:
                errors.append(f"support must be list of <= {_MAX_SUPPORT} entries")
            else:
                for i, s in enumerate(support):
                    if not isinstance(s, str) or not s.strip():
                        errors.append(f"support[{i}] must be non-empty string")
        margin = content.get("margin_label")
        if margin is not None and not isinstance(margin, str):
            errors.append("margin_label must be a string")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        primary: list[str] = list(content["primary"])
        support: list[str] = list(content.get("support") or [])
        margin_label: str | None = content.get("margin_label")

        canvas_w = container.w
        canvas_h = container.h

        # Vertical split: top band for support (if any), bottom band
        # for primary chain. When support is empty, give all height to
        # primary so the chevrons don't look anaemic.
        if support:
            support_h = _i(canvas_h * 0.28)
            gap_v = _i(canvas_h * 0.05)
        else:
            support_h = 0
            gap_v = 0
        primary_h = canvas_h - support_h - gap_v

        # ---- support row -------------------------------------------
        sid = ctx.next_shape_id
        shapes: list[str] = []

        if support:
            n_s = len(support)
            cell_gap = canvas_w // 80
            cell_w = (canvas_w - cell_gap * (n_s - 1)) // n_s
            for i, label in enumerate(support):
                cx = container.x + i * (cell_w + cell_gap)
                cy = container.y
                shapes.append(
                    round_rect_shape(
                        sid,
                        f"vc-sup-{i}",
                        cx,
                        cy,
                        cell_w,
                        support_h,
                        "FFFFFF",
                        corner_radius_pct=8,
                        shadow=True,
                    )
                )
                sid += 1
                # Thin colored top strip for visual coding (muted) so
                # support reads as "secondary" vs primary chevrons.
                strip_h = max(_i(canvas_h * 0.012), 18000)
                shapes.append(
                    rect_shape(
                        sid,
                        f"vc-sup-strip-{i}",
                        cx,
                        cy,
                        cell_w,
                        strip_h,
                        p.muted,
                    )
                )
                sid += 1
                shapes.append(
                    text_box(
                        sid,
                        f"vc-sup-lbl-{i}",
                        cx + 60000,
                        cy + strip_h + 30000,
                        cell_w - 120000,
                        support_h - strip_h - 60000,
                        label,
                        size_pt=11,
                        bold=True,
                        color=p.dark,
                        font=ctx.font,
                        align="ctr",
                    )
                )
                sid += 1

        # ---- primary chevron chain ----------------------------------
        primary_y = container.y + support_h + gap_v
        n_p = len(primary)

        # Reserve a small slice on the right for the margin cap when present.
        if margin_label:
            margin_w = _i(canvas_w * 0.07)
            margin_gap = _i(canvas_w * 0.005)
        else:
            margin_w = 0
            margin_gap = 0
        chain_w = canvas_w - margin_w - margin_gap

        # Chevrons interlock — make them slightly overlap by the indent
        # depth so the convex tip of one fits into the concave of the
        # next, like Porter's classic diagram.
        indent_pct = 35
        # Each chevron's effective body width minus indent should make
        # the row sum to chain_w. Approximate: total = n*box_w - (n-1)*overlap.
        box_w = chain_w // n_p
        # Slight visual overlap (~15% of box_w) for the interlocking look.
        overlap = box_w // 7

        # Cycle accent colors so adjacent chevrons read distinctly.
        accents = [p.purple_dk, p.purple_lt, p.amber, p.green, p.purple, p.muted, p.purple_dk]

        for i, label in enumerate(primary):
            cx = container.x + i * (box_w - overlap)
            shapes.append(
                _chevron(
                    sid,
                    f"vc-pri-{i}",
                    cx,
                    primary_y,
                    box_w,
                    primary_h,
                    accents[i % len(accents)],
                    indent_pct=indent_pct,
                )
            )
            sid += 1
            # Label inset so it clears the chevron's concave left edge
            # and convex right point.
            shapes.append(
                text_box(
                    sid,
                    f"vc-pri-lbl-{i}",
                    cx + box_w // 6,
                    primary_y + 40000,
                    box_w * 2 // 3,
                    primary_h - 80000,
                    label,
                    size_pt=12,
                    bold=True,
                    color="FFFFFF",
                    font=ctx.font,
                    align="ctr",
                    auto_fit=True,
                )
            )
            sid += 1

        # ---- margin cap ---------------------------------------------
        # rtTriangle is widest on its LEFT edge and narrows to a point
        # on the right. Center-aligning text in the bounding box makes
        # it spill past the visible triangle and clip; pin the label
        # to the left half (where the triangle still has area to
        # contain text).
        if margin_label:
            mx = container.x + canvas_w - margin_w
            my = primary_y
            shapes.append(
                _right_triangle(
                    sid,
                    "vc-margin",
                    mx,
                    my,
                    margin_w,
                    primary_h,
                    p.amber,
                )
            )
            sid += 1
            label_w = margin_w // 2
            shapes.append(
                text_box(
                    sid,
                    "vc-margin-lbl",
                    mx + 20000,
                    my + primary_h // 3,
                    label_w,
                    primary_h // 3,
                    margin_label,
                    size_pt=10,
                    bold=True,
                    color="FFFFFF",
                    font=ctx.font,
                    align="ctr",
                    auto_fit=True,
                )
            )
            sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
