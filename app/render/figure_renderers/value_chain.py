"""Porter-style value chain.

Layout follows Porter's original diagram with an optional analysis
content row beneath each primary chevron:

  ┌─────────────────────────────────────────────┐
  │ Support 1                                    │
  ├─────────────────────────────────────────────┤
  │ Support 2          (vertically stacked)      │
  ├─────────────────────────────────────────────┤
  │ Support N                                    │
  └─────────────────────────────────────────────┘
   > Primary 1 > Primary 2 > … >|> 利益    (chevron header strip)
  ┌────────┐┌────────┐┌─────┐
  │ ・項目1  ││・項目1  ││…   │              (content cards, optional)
  │ ・項目2  ││・項目2  │└─────┘
  └────────┘└────────┘

When ``primary`` entries are plain strings (or have no ``items``),
the content row is suppressed and the chevrons take the full
height — recovering the original "labels-only" look. Mixed forms
work too: any primary with items triggers the content row, but
items-less primaries get an empty card under them so the
horizontal rhythm stays.

Distinct from process_flow, which is a flat strip of pills + arrows
with no support panel and no content row.
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

_MIN_PRIMARY = 3
_MAX_PRIMARY = 7
_MAX_SUPPORT = 4
_MAX_ITEMS_PER_PRIMARY = 4
_MAX_ITEMS_PER_SUPPORT = 3

_CHEVRON_INDENT_PCT = 25


def _normalize_entry(raw: Any) -> dict[str, Any] | None:
    """Coerce a primary/support entry into ``{label, items}`` form, or
    return None on invalid input. Plain strings → no items."""
    if isinstance(raw, str):
        s = raw.strip()
        return {"label": s, "items": []} if s else None
    if isinstance(raw, dict):
        label = raw.get("label")
        if not isinstance(label, str) or not label.strip():
            return None
        items_raw = raw.get("items") or []
        if not isinstance(items_raw, list):
            return None
        items = [str(it).strip() for it in items_raw if isinstance(it, str) and it.strip()]
        return {"label": label, "items": items}
    return None


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
    """Porter value chain — primary chevrons + optional support stack + per-activity content."""

    figure_type = "value_chain"
    description = (
        "Porter-style value chain. Primary activities (3-7) render as "
        "interlocking chevrons in a single brand color; optional support "
        "activities (0-4) stack vertically above as horizontal bands; an "
        "optional margin_label adds a same-height chevron cap (in amber) "
        "right after the last primary. Each primary/support entry can be "
        "a plain string (label only) OR an object {label, items[]} where "
        "items are short bullet points of analysis content rendered in "
        "white cards beneath each primary chevron (or inline next to a "
        "support label). "
        "content: {primary: [str | {label, items?}], "
        "support?: [str | {label, items?}], margin_label?: str}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "primary": [
            {"label": "購買物流", "items": ["JIT 在庫", "サプライヤ品質"]},
            {"label": "製造", "items": ["自動化", "歩留り改善"]},
            {"label": "出荷物流", "items": ["即配対応"]},
            {"label": "販売・マーケ", "items": ["直販強化", "代理店網"]},
            {"label": "サービス", "items": ["解約防止"]},
        ],
        "support": [
            {"label": "企業インフラ", "items": ["ガバナンス再整備"]},
            {"label": "人材管理", "items": ["スキル可視化"]},
            "技術開発",
            "調達",
        ],
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
            for i, raw in enumerate(primary):
                norm = _normalize_entry(raw)
                if norm is None:
                    errors.append(
                        f"primary[{i}] must be a non-empty string or "
                        f"{{label, items?}} object"
                    )
                    continue
                if len(norm["items"]) > _MAX_ITEMS_PER_PRIMARY:
                    errors.append(
                        f"primary[{i}].items must have <= {_MAX_ITEMS_PER_PRIMARY}"
                    )
        support = content.get("support")
        if support is not None:
            if not isinstance(support, list) or len(support) > _MAX_SUPPORT:
                errors.append(f"support must be list of <= {_MAX_SUPPORT} entries")
            else:
                for i, raw in enumerate(support):
                    norm = _normalize_entry(raw)
                    if norm is None:
                        errors.append(
                            f"support[{i}] must be a non-empty string or "
                            f"{{label, items?}} object"
                        )
                        continue
                    if len(norm["items"]) > _MAX_ITEMS_PER_SUPPORT:
                        errors.append(
                            f"support[{i}].items must have <= "
                            f"{_MAX_ITEMS_PER_SUPPORT}"
                        )
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

        primary_norm = [
            _normalize_entry(e) for e in content["primary"]
        ]
        # validate() already filtered, but be defensive in case of
        # in-flight schema drift.
        primary_norm = [e for e in primary_norm if e is not None]
        support_norm = [
            n
            for n in (_normalize_entry(e) for e in (content.get("support") or []))
            if n is not None
        ]
        margin_label: str | None = content.get("margin_label")

        canvas_w = container.w
        canvas_h = container.h

        has_content = any(e["items"] for e in primary_norm)

        # ---- vertical band split ----
        if support_norm:
            band_h = max(_i(canvas_h * 0.075), 220000)
            support_h = band_h * len(support_norm) + max(
                _i(canvas_h * 0.012), 18000
            ) * (len(support_norm) - 1)
            support_h = min(support_h, _i(canvas_h * 0.40))
            gap_after_support = _i(canvas_h * 0.04)
        else:
            band_h = 0
            support_h = 0
            gap_after_support = 0

        remaining = canvas_h - support_h - gap_after_support

        if has_content:
            # Header chevrons take a third of the remaining vertical
            # budget; content cards take the rest.
            chev_h = max(_i(remaining * 0.32), 380000)
            content_gap = _i(canvas_h * 0.018)
            cards_h = remaining - chev_h - content_gap
        else:
            chev_h = remaining
            content_gap = 0
            cards_h = 0

        sid = ctx.next_shape_id
        shapes: list[str] = []

        # ---- support: single panel with stacked horizontal bands ----
        if support_norm:
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

            actual_band_h = support_h // len(support_norm)
            accent_w = max(_i(0.06 * 914400), 48000)
            for i, entry in enumerate(support_norm):
                by = panel_y + i * actual_band_h
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
                # Label on the left third, items inline on the right.
                label_w = (panel_w - accent_w) // 3
                items_x = panel_x + accent_w + 80000 + label_w
                items_w = panel_w - (items_x - panel_x) - 60000
                shapes.append(
                    text_box(
                        sid,
                        f"vc-sup-lbl-{i}",
                        panel_x + accent_w + 80000,
                        by,
                        label_w,
                        actual_band_h,
                        entry["label"],
                        size_pt=11,
                        bold=True,
                        color=p.dark,
                        font=ctx.font,
                        align="l",
                    )
                )
                sid += 1
                if entry["items"]:
                    items_text = "  /  ".join(entry["items"])
                    shapes.append(
                        text_box(
                            sid,
                            f"vc-sup-items-{i}",
                            items_x,
                            by,
                            items_w,
                            actual_band_h,
                            items_text,
                            size_pt=9,
                            color=p.muted,
                            font=ctx.font,
                            align="l",
                        )
                    )
                    sid += 1
                if i < len(support_norm) - 1:
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

        # ---- chevron strip ----
        primary_y = container.y + support_h + gap_after_support
        n_p = len(primary_norm)
        margin_present = bool(margin_label)
        if margin_present:
            denom = (n_p + 1) - n_p * (_CHEVRON_INDENT_PCT / 100.0)
        else:
            denom = n_p - (n_p - 1) * (_CHEVRON_INDENT_PCT / 100.0)
        box_w = int(canvas_w / denom)
        indent_emu = int(box_w * _CHEVRON_INDENT_PCT / 100)
        step = box_w - indent_emu

        for i, entry in enumerate(primary_norm):
            cx = container.x + i * step
            shapes.append(
                _chevron(
                    sid,
                    f"vc-pri-{i}",
                    cx,
                    primary_y,
                    box_w,
                    chev_h,
                    p.purple_dk,
                )
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"vc-pri-lbl-{i}",
                    cx + indent_emu,
                    primary_y + 30000,
                    box_w - 2 * indent_emu,
                    chev_h - 60000,
                    entry["label"],
                    size_pt=12,
                    bold=True,
                    color="FFFFFF",
                    font=ctx.font,
                    align="ctr",
                    auto_fit=True,
                )
            )
            sid += 1

        if margin_present:
            mx = container.x + n_p * step
            shapes.append(
                _chevron(
                    sid,
                    "vc-margin",
                    mx,
                    primary_y,
                    box_w,
                    chev_h,
                    p.amber,
                )
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    "vc-margin-lbl",
                    mx + indent_emu,
                    primary_y + 30000,
                    box_w - 2 * indent_emu,
                    chev_h - 60000,
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

        # ---- content cards (one per primary, aligned with chevron) ----
        if has_content:
            cards_y = primary_y + chev_h + content_gap
            card_inset = max(step // 24, 30000)
            for i, entry in enumerate(primary_norm):
                cx = container.x + i * step + card_inset
                card_w = step - 2 * card_inset
                shapes.append(
                    round_rect_shape(
                        sid,
                        f"vc-card-{i}",
                        cx,
                        cards_y,
                        card_w,
                        cards_h,
                        "FFFFFF",
                        corner_radius_pct=8,
                        shadow=True,
                    )
                )
                sid += 1
                if entry["items"]:
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
                        for it in entry["items"][:_MAX_ITEMS_PER_PRIMARY]
                    ]
                    shapes.append(
                        text_box_paragraphs(
                            sid,
                            f"vc-card-items-{i}",
                            cx + 50000,
                            cards_y + 40000,
                            card_w - 100000,
                            cards_h - 80000,
                            paragraphs,
                            font=ctx.font,
                            anchor="t",
                            auto_fit=True,
                        )
                    )
                    sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
