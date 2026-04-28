"""Porter-style value chain.

Layout follows Porter's original diagram:

  ┌─────────────────────────────────────────────┐
  │ Support 1                                    │
  ├─────────────────────────────────────────────┤
  │ Support 2          (vertically stacked)      │
  ├─────────────────────────────────────────────┤
  │ Support 3                                    │
  └─────────────────────────────────────────────┘
   > Primary 1 > Primary 2 > Primary 3 > … >|> 利益
   (interlocking chevrons, all the brand color)

Distinct from process_flow, which is a flat strip of pills + arrows
with no support panel and no margin cap.
"""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import _i, _xml_escape, rect_shape, round_rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MIN_PRIMARY = 3
_MAX_PRIMARY = 7
_MAX_SUPPORT = 4

# Indent/notch depth as a percentage of chevron width. 25% is a
# common Porter-style proportion: deep enough to read as an arrow,
# shallow enough that the next chevron has room for its label.
_CHEVRON_INDENT_PCT = 25


def _chevron(
    sp_id: int,
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    fill: str,
    *,
    indent_pct: int = _CHEVRON_INDENT_PCT,
    shadow: bool = True,
) -> str:
    """Right-pointing chevron (left side concave, right side convex).
    `indent_pct` 0..100 controls how deep the indent / point is."""
    indent = max(0, min(100, indent_pct))
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
        f'<a:prstGeom prst="chevron">'
        f'<a:avLst><a:gd name="adj" fmla="val {indent * 1000}"/></a:avLst>'
        f'</a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
        f'<a:ln><a:noFill/></a:ln>'
        f"{effect}"
        f"</p:spPr>"
        f'<p:txBody><a:bodyPr wrap="square" anchor="ctr"/><a:lstStyle/><a:p/></p:txBody>'
        f"</p:sp>"
    )


@register
class ValueChainRenderer(FigureRenderer):
    """Porter value chain — primary chevrons + optional support stack + margin cap."""

    figure_type = "value_chain"
    description = (
        "Porter-style value chain. Primary activities (3-7) render as "
        "interlocking chevrons in a single brand color; optional "
        "support activities (0-4) stack vertically above as horizontal "
        "bands; an optional margin_label adds a same-height chevron "
        "cap (in amber) right after the last primary. "
        "content: {primary: [str, ...], support?: [str, ...], margin_label?: str}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "primary": ["調達", "製造", "物流", "販売", "サービス"],
        "support": ["企業インフラ", "人材管理", "技術開発"],
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
            for i, pr in enumerate(primary):
                if not isinstance(pr, str) or not pr.strip():
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

        # ---- vertical band split ----
        # Support stack on top (sized to fit support row count), primary
        # chevron strip below. Gap between the two so the strip reads
        # as a separate component.
        if support:
            # ~70px per support band — looks substantive enough that
            # they don't read as razor-thin filler.
            band_h = max(_i(canvas_h * 0.075), 220000)
            support_h = band_h * len(support) + max(_i(canvas_h * 0.012), 18000) * (
                len(support) - 1
            )
            support_h = min(support_h, _i(canvas_h * 0.45))
            gap_v = _i(canvas_h * 0.05)
        else:
            band_h = 0
            support_h = 0
            gap_v = 0
        primary_h = canvas_h - support_h - gap_v

        sid = ctx.next_shape_id
        shapes: list[str] = []

        # ---- support: single panel with stacked horizontal bands ----
        if support:
            panel_x = container.x
            panel_y = container.y
            panel_w = canvas_w
            shapes.append(
                round_rect_shape(
                    sid,
                    "vc-support-panel",
                    panel_x,
                    panel_y,
                    panel_w,
                    support_h,
                    "FFFFFF",
                    corner_radius_pct=4,
                    shadow=True,
                )
            )
            sid += 1

            # Each support band: full-width row with bottom divider.
            actual_band_h = support_h // len(support)
            for i, label in enumerate(support):
                by = panel_y + i * actual_band_h
                # Subtle row tint so support reads as one panel with
                # internal divisions instead of one flat block.
                if i % 2 == 1:
                    shapes.append(
                        rect_shape(
                            sid,
                            f"vc-sup-bg-{i}",
                            panel_x + 12000,
                            by,
                            panel_w - 24000,
                            actual_band_h,
                            "F8F6FB",
                        )
                    )
                    sid += 1
                # Left accent bar to align with primary's purple.
                accent_w = max(_i(0.06 * 914400), 48000)
                shapes.append(
                    rect_shape(
                        sid,
                        f"vc-sup-acc-{i}",
                        panel_x,
                        by,
                        accent_w,
                        actual_band_h,
                        p.purple_lt,
                    )
                )
                sid += 1
                shapes.append(
                    text_box(
                        sid,
                        f"vc-sup-lbl-{i}",
                        panel_x + accent_w + 80000,
                        by,
                        panel_w - accent_w - 160000,
                        actual_band_h,
                        label,
                        size_pt=11,
                        bold=True,
                        color=p.dark,
                        font=ctx.font,
                        align="l",
                    )
                )
                sid += 1
                # Bottom divider (skip the last row).
                if i < len(support) - 1:
                    shapes.append(
                        rect_shape(
                            sid,
                            f"vc-sup-div-{i}",
                            panel_x + accent_w + 40000,
                            by + actual_band_h - 4000,
                            panel_w - accent_w - 80000,
                            8000,
                            p.border,
                        )
                    )
                    sid += 1

        # ---- primary chevrons + optional margin cap ----
        primary_y = container.y + support_h + gap_v
        # Vertically center the chevron strip a touch shorter than the
        # full primary band so its shadow has room to breathe.
        chev_h = max(_i(primary_h * 0.78), 600000)
        chev_y = primary_y + (primary_h - chev_h) // 2

        n_p = len(primary)
        # Spacing math: each chevron is `box_w` wide, but the next one
        # nestles into its right tip by `indent_emu`. So the per-step
        # advance is `(box_w - indent_emu)` and the very last chevron
        # contributes its full box_w. With an optional margin chevron
        # of equal height, that adds another (box_w - indent_emu) for
        # its overlap into the chain plus margin_w for its visible
        # extent.
        margin_present = bool(margin_label)
        # Rough sizing first pass — assume margin chevron is the same
        # box_w as primary; we'll back the math out from total width.
        if margin_present:
            # n_p primary + 1 margin chevron interlocked
            denom = (n_p + 1) - n_p * (_CHEVRON_INDENT_PCT / 100.0)
        else:
            denom = n_p - (n_p - 1) * (_CHEVRON_INDENT_PCT / 100.0)
        box_w = int(canvas_w / denom)
        indent_emu = int(box_w * _CHEVRON_INDENT_PCT / 100)
        step = box_w - indent_emu

        for i, label in enumerate(primary):
            cx = container.x + i * step
            shapes.append(
                _chevron(
                    sid,
                    f"vc-pri-{i}",
                    cx,
                    chev_y,
                    box_w,
                    chev_h,
                    p.purple_dk,
                    indent_pct=_CHEVRON_INDENT_PCT,
                )
            )
            sid += 1
            # Label inset so it clears the chevron's concave left edge
            # and convex right point.
            shapes.append(
                text_box(
                    sid,
                    f"vc-pri-lbl-{i}",
                    cx + indent_emu,
                    chev_y + 40000,
                    box_w - 2 * indent_emu,
                    chev_h - 80000,
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

        # Margin chevron — same shape as the primary ones so it reads
        # as the natural end of the chain. Amber so it stands out as
        # the "result" the chain produces.
        if margin_present:
            mx = container.x + n_p * step
            shapes.append(
                _chevron(
                    sid,
                    "vc-margin",
                    mx,
                    chev_y,
                    box_w,
                    chev_h,
                    p.amber,
                    indent_pct=_CHEVRON_INDENT_PCT,
                )
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    "vc-margin-lbl",
                    mx + indent_emu,
                    chev_y + 40000,
                    box_w - 2 * indent_emu,
                    chev_h - 80000,
                    margin_label,
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
