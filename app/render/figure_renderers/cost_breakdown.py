"""Cost breakdown: total header + itemized horizontal bar chart with amounts."""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import fit_stack, h_line, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_MAX_ITEMS = 8


def _fmt_amount(amt: float, currency: str | None) -> str:
    """Format number with thousand separators and optional currency prefix."""
    s = f"{amt:,.0f}" if amt == int(amt) else f"{amt:,.2f}"
    return f"{currency}{s}" if currency else s


@register
class CostBreakdownRenderer(FigureRenderer):
    """Cost breakdown: total line on top + items as horizontal bar chart."""

    figure_type = "cost_breakdown"
    description = (
        "Cost breakdown with total header and itemized horizontal bars. "
        "content: {total: {label, amount, currency?}, items: [{label, amount}]}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "total": {"label": "合計", "amount": 1000000, "currency": "¥"},
        "items": [
            {"label": "項目1", "amount": 600000},
            {"label": "項目2", "amount": 400000},
        ],
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        total = content.get("total")
        if not isinstance(total, dict):
            errors.append("total must be object")
        else:
            if not total.get("label"):
                errors.append("total.label required")
            amt = total.get("amount")
            if not isinstance(amt, (int, float)) or isinstance(amt, bool):
                errors.append("total.amount must be number")
        items = content.get("items")
        if not isinstance(items, list) or not items:
            errors.append("items must be non-empty list")
        elif len(items) > _MAX_ITEMS:
            errors.append(f"items length must be <= {_MAX_ITEMS}")
        else:
            for i, it in enumerate(items):
                if not isinstance(it, dict):
                    errors.append(f"items[{i}] must be object")
                    continue
                if not it.get("label"):
                    errors.append(f"items[{i}].label required")
                if not isinstance(it.get("amount"), (int, float)) or isinstance(
                    it.get("amount"), bool
                ):
                    errors.append(f"items[{i}].amount must be number")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        total: dict[str, Any] = content["total"]
        items: list[dict[str, Any]] = list(content["items"])[:_MAX_ITEMS]
        currency = total.get("currency") or ""
        total_amount = float(total["amount"])

        total_h = 560000
        rule_y = container.y + total_h + 40000
        body_y = rule_y + 60000
        body_h = container.h - (body_y - container.y)

        shapes: list[str] = []
        sid = ctx.next_shape_id

        shapes.append(
            text_box(
                sid,
                "cb-total-lbl",
                container.x,
                container.y,
                container.w // 2,
                total_h,
                str(total["label"]),
                size_pt=14,
                bold=True,
                color=p.purple_dk,
                font=ctx.font,
            )
        )
        sid += 1
        shapes.append(
            text_box(
                sid,
                "cb-total-amt",
                container.x + container.w // 2,
                container.y,
                container.w // 2,
                total_h,
                _fmt_amount(total_amount, currency),
                size_pt=22,
                bold=True,
                color=p.purple_dk,
                align="r",
                font=ctx.font,
            )
        )
        sid += 1

        shapes.append(
            h_line(sid, "cb-rule", container.x, rule_y, container.w, p.border)
        )
        sid += 1

        n = len(items)
        row_h, row_gap = fit_stack(
            container_h=body_h,
            n=n,
            natural_h=460000,
            min_h=180000,
            gap=40000,
            min_gap=10000,
        )
        label_w = container.w * 30 // 100
        amount_w = container.w * 18 // 100
        bar_track_x = container.x + label_w + 40000
        bar_track_w = container.w - label_w - amount_w - 80000

        max_amt = max((float(it["amount"]) for it in items), default=1.0)
        if max_amt <= 0:
            max_amt = 1.0

        for i, it in enumerate(items):
            amt = float(it["amount"])
            y = body_y + (row_h + row_gap) * i
            bar_h = max(60000, min(row_h - 80000, 280000))
            by = y + (row_h - bar_h) // 2
            bw = max(round(bar_track_w * (amt / max_amt)), 20000)

            shapes.append(
                text_box(
                    sid,
                    f"cb-lbl-{i}",
                    container.x,
                    by,
                    label_w,
                    bar_h,
                    str(it["label"]),
                    size_pt=10,
                    bold=True,
                    color=p.black,
                    font=ctx.font,
                    auto_fit=True,
                )
            )
            sid += 1
            shapes.append(
                rect_shape(
                    sid,
                    f"cb-track-{i}",
                    bar_track_x,
                    by,
                    bar_track_w,
                    bar_h,
                    p.bg_alt,
                )
            )
            sid += 1
            shapes.append(
                rect_shape(sid, f"cb-bar-{i}", bar_track_x, by, bw, bar_h, p.purple)
            )
            sid += 1
            shapes.append(
                text_box(
                    sid,
                    f"cb-amt-{i}",
                    container.x + container.w - amount_w,
                    by,
                    amount_w,
                    bar_h,
                    _fmt_amount(amt, currency),
                    size_pt=10,
                    bold=True,
                    color=p.dark,
                    align="r",
                    font=ctx.font,
                )
            )
            sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
