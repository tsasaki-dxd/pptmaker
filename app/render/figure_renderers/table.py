"""Table figure renderer with alternating row fills."""

from __future__ import annotations

from typing import Any, ClassVar

from ..shapes import fit_stack, rect_shape, text_box
from ..typography import TYPE_SCALE as T
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

# When the body slot is narrow vertically, fit_stack hands back row
# heights that auto_fit would shrink the text into invisibility on.
# Cap the per-slide row count so the renderer can either reject
# overflow (forcing the blueprint LLM to split) or render at a usable
# minimum size. Tables larger than this are typically supporting data
# that belongs across multiple slides anyway.
_MAX_ROWS = 14


@register
class TableRenderer(FigureRenderer):
    figure_type = "table"
    description = (
        "Rows × columns table with alternating background, header pill, "
        "first-column emphasis. "
        "content: {title?: str, headers: [str], rows: [[str]]}. "
        f"Hard cap: {_MAX_ROWS} rows per slide — when content has more, "
        "split into multiple table slides by topic / phase rather than "
        "letting the renderer reject the whole figure."
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
        elif len(rows) > _MAX_ROWS:
            errors.append(
                f"rows length {len(rows)} exceeds max {_MAX_ROWS}; "
                "split this table across multiple slides"
            )
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
        # 14 rows → squeezed proportionally so the table doesn't run
        # off the bottom of the slot. Floor dropped from 160k → 110k
        # so dense tables on shorter body slots still fit without
        # auto_fit having to scale text into invisibility.
        row_h, _ = fit_stack(
            container_h=container.h,
            n=len(rows),
            natural_h=380000,
            min_h=110000,
            gap=0,
            min_gap=0,
            header_h=header_h,
        )

        # Auto-shrink the body font on dense tables. Above ~10 rows the
        # natural row_h drops below the comfortable line height for
        # 10pt and PowerPoint's spAutoFit scales aggressively.
        body_size = T["label"] if len(rows) <= 10 else T["caption"]

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
                    size_pt=T["label"],
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
                # Cell text gets the full row_h so the text box is tall
                # enough that auto_fit doesn't have to scale the font
                # down. Auto_fit is OFF — at fixed body_size with the
                # row count cap, JP text always fits without scaling,
                # and disabling it prevents the "text shrinks to dust"
                # failure mode the user hit on dense tables.
                shapes.append(
                    text_box(
                        sid,
                        f"td-{r}-{c}",
                        container.x + col_w * c + 80000,
                        y,
                        col_w - 160000,
                        row_h,
                        str(cell),
                        size_pt=body_size,
                        bold=(c == 0),
                        color=p.black,
                        font=ctx.font,
                        auto_fit=False,
                    )
                )
                sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
