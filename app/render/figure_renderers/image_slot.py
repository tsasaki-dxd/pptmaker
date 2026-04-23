"""Image slot placeholder stub (real <p:pic> embedding in Phase 2.3 Track J)."""

from __future__ import annotations

from typing import Any

from ..shapes import rect_outline, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

_FIT_VALUES = ("cover", "contain", "fill", "fit_width")


@register
class ImageSlotRenderer(FigureRenderer):
    """Stub placeholder for an image asset. Real <p:pic> embedding is Phase 2.3 J."""

    figure_type = "image_slot"
    description = (
        "Image slot placeholder (stub). Real <p:pic> embedding is Phase 2.3 Track J. "
        "content: {asset_id, caption?, alt?, fit?}"
    )

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        asset_id = content.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id.strip():
            errors.append("asset_id required (non-empty string)")
        fit = content.get("fit")
        if fit is not None and fit not in _FIT_VALUES:
            errors.append(f"fit must be one of {_FIT_VALUES}")
        caption = content.get("caption")
        if caption is not None and not isinstance(caption, str):
            errors.append("caption must be string")
        alt = content.get("alt")
        if alt is not None and not isinstance(alt, str):
            errors.append("alt must be string")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        # TODO(phase2.3-track-J): replace stub with real <p:pic> embed using
        # asset_id -> presigned S3 bytes + media/image{n}.png part in the PPTX.
        p = ctx.palette
        asset_id = str(content["asset_id"])
        caption = str(content.get("caption") or "")
        short_id = asset_id[:8] + "..." if len(asset_id) > 8 else asset_id

        shapes: list[str] = []
        sid = ctx.next_shape_id

        shapes.append(
            rect_shape(
                sid, "img-bg", container.x, container.y, container.w, container.h, p.bg_alt
            )
        )
        sid += 1
        shapes.append(
            rect_outline(
                sid,
                "img-out",
                container.x,
                container.y,
                container.w,
                container.h,
                p.border,
            )
        )
        sid += 1

        caption_h = 320000 if caption else 0
        title_h = 320000
        title_y = container.y + (container.h - title_h - caption_h) // 2

        shapes.append(
            text_box(
                sid,
                "img-title",
                container.x + 160000,
                title_y,
                container.w - 320000,
                title_h,
                f"画像スロット ({short_id})",
                size_pt=12,
                bold=True,
                color=p.muted,
                align="ctr",
                font=ctx.font,
            )
        )
        sid += 1

        if caption:
            shapes.append(
                text_box(
                    sid,
                    "img-caption",
                    container.x + 160000,
                    title_y + title_h + 40000,
                    container.w - 320000,
                    caption_h,
                    caption,
                    size_pt=10,
                    color=p.dark,
                    align="ctr",
                    font=ctx.font,
                )
            )
            sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)
