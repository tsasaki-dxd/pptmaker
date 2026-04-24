"""Table figure renderer with alternating row fills."""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import fit_stack, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register


@register
class TableRenderer(FigureRenderer):
    figure_type = "table"
    description = (
        "Rows × columns table with alternating background, header pill, first-column emphasis. "
        "content: {title?: str, headers: [str], rows: [[str]]}"
    )
    input_schema_example: ClassVar[dict[str, Any]] = {
        "title": "見出し",
        "headers": ["列1", "列2"],
        "rows": [["a", "b"], ["c", "d"]],
    }

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors = []
        if not isinstance(content.get("headers"), list) or len(content["headers"]) < 2:
            errors.append("headers must be list of length >= 2")
        rows = content.get("rows")
        if not isinstance(rows, list) or not rows:
            errors.append("rows must be non-empty list")
        elif any(not isinstance(r, list) for r in rows):
            errors.append("each row must be a list")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
        headers: list[str] = content["headers"]
        rows: list[list[str]] = content["rows"]
        ncols = len(headers)

        col_w = container.w // ncols
        header_h = 400000
        # row_h shrinks with row count: 5 rows → 380k each (natural),
        # 15 rows → squeezed proportionally so the table doesn't run
        # off the bottom of the slot. Floored at 160k EMU.
        row_h, _ = fit_stack(
            container_h=container.h,
            n=len(rows),
            natural_h=380000,
            min_h=160000,
            gap=0,
            min_gap=0,
            header_h=header_h,
        )

        shapes: list[str] = []
        sid = ctx.next_shape_id

        # Header
        shapes.append(
            rect_shape(sid, "table-header", container.x, container.y, container.w, header_h, p.purple)
        )
        sid += 1
        for i, head in enumerate(headers):
            shapes.append(
                text_box(
                    sid,
                    f"th-{i}",
                    container.x + col_w * i + 80000,
                    container.y + 80000,
                    col_w - 160000,
                    header_h - 160000,
                    head,
                    size_pt=10,
                    bold=True,
                    color="FFFFFF",
                    font=ctx.font,
                )
            )
            sid += 1

        # Body rows with alternating fill
        for r, row in enumerate(rows):
            y = container.y + header_h + row_h * r
            fill = p.bg_alt if r % 2 == 0 else "FFFFFF"
            shapes.append(rect_shape(sid, f"tr-{r}", container.x, y, container.w, row_h, fill))
            sid += 1
            for c, cell in enumerate(row[:ncols]):
                shapes.append(
                    text_box(
                        sid,
                        f"td-{r}-{c}",
                        container.x + col_w * c + 80000,
                        y + 70000,
                        col_w - 160000,
                        max(80000, row_h - 140000),
                        str(cell),
                        size_pt=10,
                        bold=(c == 0),
                        color=p.black,
                        font=ctx.font,
                        auto_fit=True,
                    )
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
