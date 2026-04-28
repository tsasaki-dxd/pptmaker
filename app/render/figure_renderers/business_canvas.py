"""Business Model Canvas — Osterwalder's 9-box layout.

Fixed grid:

  ┌──────┬──────┬─────────┬──────┬──────┐
  │ KP   │ KA   │         │ CR   │      │
  │      ├──────┤   VP    ├──────┤  CS  │
  │      │ KR   │         │ CH   │      │
  ├──────┴──────┴─────────┴──────┴──────┤
  │  Cost Structure    │ Revenue Streams│
  └────────────────────┴────────────────┘

Each section title is the canonical English name (with a JP gloss
in parens) so the diagram is recognisable to anyone who's ever
seen a BMC. Items render as bullet lines inside the section card.
"""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import (
    TextParagraph,
    TextRun,
    _i,
    round_rect_shape,
    text_box,
    text_box_paragraphs,
)
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

# Section keys are the BMC canonical names (snake_case). Titles are
# JP-only because the half-column cells are too narrow for the full
# English+JP gloss to fit on one line; wrapping made the title bleed
# into the items area underneath. Operators recognise the standard
# BMC sections from the JP labels alone.
_SECTIONS: list[tuple[str, str]] = [
    ("key_partners", "主要パートナー"),
    ("key_activities", "主要活動"),
    ("key_resources", "主要リソース"),
    ("value_propositions", "価値提案"),
    ("customer_relationships", "顧客関係"),
    ("channels", "チャネル"),
    ("customer_segments", "顧客セグメント"),
    ("cost_structure", "コスト構造"),
    ("revenue_streams", "収益の流れ"),
]
_SECTION_KEYS = {k for k, _ in _SECTIONS}
_REQUIRED_KEYS = _SECTION_KEYS  # all 9 are required for the canvas to read right
_MAX_ITEMS_PER_SECTION = 6


@register
class BusinessCanvasRenderer(FigureRenderer):
    """Business Model Canvas — fixed 9-box Osterwalder layout."""

    figure_type = "business_canvas"
    description = (
        "Business Model Canvas (Osterwalder). All 9 sections are required. "
        "Items render as a bullet list per section. "
        "content keys: key_partners, key_activities, key_resources, "
        "value_propositions, customer_relationships, channels, "
        "customer_segments, cost_structure, revenue_streams. "
        "Each is a list of short strings (<= 6 entries)."
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "key_partners": ["AWS", "決済プロバイダ", "OEM パートナー"],
        "key_activities": ["プラットフォーム開発", "顧客サポート"],
        "key_resources": ["技術者チーム", "顧客データ"],
        "value_propositions": [
            "短納期 (4週間)",
            "投資回収 12ヶ月",
            "国内 50社の実績",
        ],
        "customer_relationships": ["CSM 専任", "オンラインコミュニティ"],
        "channels": ["直販", "代理店", "Web セルフサーブ"],
        "customer_segments": ["中堅製造業", "公共"],
        "cost_structure": ["人件費 60%", "クラウド 20%", "営業 15%"],
        "revenue_streams": ["月額サブスク", "従量課金", "コンサル"],
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        for key in sorted(_REQUIRED_KEYS):
            v = content.get(key)
            if not isinstance(v, list):
                errors.append(f"{key} must be a list (got {type(v).__name__})")
                continue
            if len(v) > _MAX_ITEMS_PER_SECTION:
                errors.append(
                    f"{key} must have <= {_MAX_ITEMS_PER_SECTION} entries"
                )
            for i, it in enumerate(v):
                if not isinstance(it, str) or not it.strip():
                    errors.append(f"{key}[{i}] must be non-empty string")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        cw = container.w
        ch = container.h

        # Vertical split: top 5-column band (~70%), bottom 2-column
        # band (~30%) for cost / revenue.
        top_h = _i(ch * 0.70)
        bot_h = ch - top_h
        gap = max(_i(min(cw, ch) * 0.008), 12000)

        # 5 equal columns across the top band.
        col_w = cw // 5

        # Per-section box (col, row, w_units, h_units) where units are
        # in (cols, half-rows). KA + KR stack inside col 1, CR + CH
        # stack inside col 3, all others fill their full column.
        # Format: (key, x_idx, y_idx, w_idx, h_idx)
        # x_idx 0..4, y_idx 0 = top half, 1 = bottom half (in 5-col band).
        layout_top: list[tuple[str, int, int, int, int]] = [
            ("key_partners", 0, 0, 1, 2),
            ("key_activities", 1, 0, 1, 1),
            ("key_resources", 1, 1, 1, 1),
            ("value_propositions", 2, 0, 1, 2),
            ("customer_relationships", 3, 0, 1, 1),
            ("channels", 3, 1, 1, 1),
            ("customer_segments", 4, 0, 1, 2),
        ]
        half_h = top_h // 2

        sid = ctx.next_shape_id
        shapes: list[str] = []

        for key, xi, yi, wi, hi in layout_top:
            x = container.x + xi * col_w
            y = container.y + yi * half_h
            w = wi * col_w - gap
            h = hi * half_h - gap
            shapes.extend(
                self._draw_section(
                    sid,
                    key=key,
                    items=content[key],
                    x=x,
                    y=y,
                    w=w,
                    h=h,
                    palette=p,
                    font=ctx.font,
                )
            )
            sid += 4 + min(len(content[key]), _MAX_ITEMS_PER_SECTION)

        # Bottom row: cost (60%) + revenue (40%)
        bot_y = container.y + top_h
        cost_w = (cw * 60) // 100 - gap
        rev_x = container.x + (cw * 60) // 100
        rev_w = (cw * 40) // 100
        shapes.extend(
            self._draw_section(
                sid,
                key="cost_structure",
                items=content["cost_structure"],
                x=container.x,
                y=bot_y,
                w=cost_w,
                h=bot_h - gap,
                palette=p,
                font=ctx.font,
            )
        )
        sid += 4 + min(len(content["cost_structure"]), _MAX_ITEMS_PER_SECTION)
        shapes.extend(
            self._draw_section(
                sid,
                key="revenue_streams",
                items=content["revenue_streams"],
                x=rev_x,
                y=bot_y,
                w=rev_w,
                h=bot_h - gap,
                palette=p,
                font=ctx.font,
            )
        )

        next_id = ctx.next_shape_id + 4 * 9 + sum(
            min(len(content[k]), _MAX_ITEMS_PER_SECTION) for k in _SECTION_KEYS
        )
        return RenderOutput(shapes_xml=shapes, next_shape_id=next_id)

    @staticmethod
    def _draw_section(
        sp_id: int,
        *,
        key: str,
        items: list[str],
        x: int,
        y: int,
        w: int,
        h: int,
        palette: Any,
        font: str,
    ) -> list[str]:
        # Per-section accent color so each box reads distinctly without
        # having to label it twice. Cost / revenue get amber + green to
        # call out the financial bottom row.
        accents = {
            "key_partners": palette.purple_lt,
            "key_activities": palette.purple,
            "key_resources": palette.purple,
            "value_propositions": palette.purple_dk,
            "customer_relationships": palette.purple,
            "channels": palette.purple,
            "customer_segments": palette.purple_lt,
            "cost_structure": palette.amber,
            "revenue_streams": palette.green,
        }
        title_lookup = {k: t for k, t in _SECTIONS}
        title = title_lookup[key]
        accent = accents.get(key, palette.purple_dk)

        # Card body
        out: list[str] = [
            round_rect_shape(
                sp_id,
                f"bmc-{key}",
                x,
                y,
                w,
                h,
                "FFFFFF",
                corner_radius_pct=8,
                shadow=True,
            )
        ]
        sid = sp_id + 1

        # Tiny accent strip on top edge.
        from ..shapes import rect_shape as _rect

        strip_h = max(_i(h * 0.06), 18000)
        out.append(_rect(sid, f"bmc-strip-{key}", x, y, w, strip_h, accent))
        sid += 1

        # Title sits in a fixed-height band above the items list. JP
        # titles fit on one line at this width, so a single-line band
        # (~22% of the card height) is plenty.
        title_band_h = max(_i(h * 0.22), 220000)
        out.append(
            text_box(
                sid,
                f"bmc-title-{key}",
                x + 40000,
                y + strip_h + 20000,
                w - 80000,
                title_band_h,
                title,
                size_pt=10,
                bold=True,
                color=palette.dark,
                font=font,
                align="l",
            )
        )
        sid += 1

        # Items as bullet paragraphs
        if items:
            paragraphs = [
                TextParagraph(
                    runs=(
                        TextRun(
                            text="・ " + str(it),
                            size_pt=8,
                            color=palette.black,
                        ),
                    ),
                    align="l",
                    space_before_pt=2,
                )
                for it in items[:_MAX_ITEMS_PER_SECTION]
            ]
            items_y = y + strip_h + 20000 + title_band_h
            items_h = max(h - (items_y - y) - 30000, 0)
            out.append(
                text_box_paragraphs(
                    sid,
                    f"bmc-items-{key}",
                    x + 40000,
                    items_y,
                    w - 80000,
                    items_h,
                    paragraphs,
                    font=font,
                    anchor="t",
                    auto_fit=True,
                )
            )
            sid += 1

        return out
