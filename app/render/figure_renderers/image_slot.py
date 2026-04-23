"""Image slot renderer with real <p:pic> embedding (Phase 2.3 Track J)."""

from __future__ import annotations

import logging
from typing import Any

from ..shapes import _i, _xml_escape, rect_outline, rect_shape, text_box
from .base import EMUBox, FigureRenderer, RenderContext, RenderOutput, ValidationResult
from .registry import register

log = logging.getLogger("slideforge.render.image_slot")

_FIT_VALUES = ("cover", "contain", "fill", "fit_width")


def _compute_src_rect(
    fit: str,
    img_w: int | None,
    img_h: int | None,
    container: EMUBox,
) -> tuple[str, EMUBox]:
    """Return (srcRect XML fragment, effective container box).

    - cover: crop image (srcRect) to match container aspect.
    - contain: shrink and center container to match image aspect; no srcRect.
    - fill: no srcRect; full stretch to container.
    - fit_width: scale container height to image aspect; no srcRect.
    """
    if not img_w or not img_h or img_w <= 0 or img_h <= 0:
        return "", container

    img_ar = img_w / img_h
    box_ar = container.w / container.h if container.h > 0 else img_ar

    if fit == "cover":
        if img_ar > box_ar:
            crop_w = img_h * box_ar
            l_pct = (img_w - crop_w) / 2 / img_w
            left = _i(l_pct * 100000)
            return (
                f'<a:srcRect l="{left}" t="0" r="{left}" b="0"/>',
                container,
            )
        elif img_ar < box_ar:
            crop_h = img_w / box_ar
            t_pct = (img_h - crop_h) / 2 / img_h
            top = _i(t_pct * 100000)
            return (
                f'<a:srcRect l="0" t="{top}" r="0" b="{top}"/>',
                container,
            )
        return '<a:srcRect l="0" t="0" r="0" b="0"/>', container

    if fit == "contain":
        if img_ar > box_ar:
            new_h = _i(container.w / img_ar)
            new_y = container.y + (container.h - new_h) // 2
            return "", EMUBox(x=container.x, y=new_y, w=container.w, h=new_h)
        elif img_ar < box_ar:
            new_w = _i(container.h * img_ar)
            new_x = container.x + (container.w - new_w) // 2
            return "", EMUBox(x=new_x, y=container.y, w=new_w, h=container.h)
        return "", container

    if fit == "fit_width":
        new_h = _i(container.w / img_ar)
        return "", EMUBox(x=container.x, y=container.y, w=container.w, h=new_h)

    return "", container


def _pic_xml(
    sp_id: int,
    name: str,
    rid: str,
    box: EMUBox,
    src_rect: str,
    alt: str,
) -> str:
    x, y, w, h = _i(box.x), _i(box.y), _i(box.w), _i(box.h)
    descr = _xml_escape(alt) if alt else ""
    return (
        f"<p:pic>"
        f'<p:nvPicPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}" descr="{descr}"/>'
        f"<p:cNvPicPr><a:picLocks noChangeAspect=\"1\"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>"
        f'<p:blipFill><a:blip r:embed="{rid}"/>'
        f"{src_rect}"
        f"<a:stretch><a:fillRect/></a:stretch></p:blipFill>"
        f"<p:spPr>"
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f"</p:spPr>"
        f"</p:pic>"
    )


@register
class ImageSlotRenderer(FigureRenderer):
    """Embeds an image asset as a <p:pic> when resolved; falls back to stub."""

    figure_type = "image_slot"
    description = (
        "Image slot. content: {asset_id, caption?, alt?, fit?}. "
        "fit ∈ {cover, contain, fill, fit_width} (default cover)."
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
        asset_id = str(content["asset_id"])
        caption = str(content.get("caption") or "")
        alt = str(content.get("alt") or "")
        fit = str(content.get("fit") or "cover")

        if ctx.media is None or asset_id not in ctx.media.resolved:
            log.warning("画像未解決: %s", asset_id[:8])
            return self._render_stub(asset_id, caption, container, ctx)

        desc = ctx.media.resolved[asset_id]
        rid = ctx.media.register(desc, ctx.slide_index or 0)

        caption_h = 320000 if caption else 0
        pic_container = EMUBox(
            x=container.x,
            y=container.y,
            w=container.w,
            h=container.h - caption_h,
        )
        src_rect, effective_box = _compute_src_rect(
            fit, desc.width_px, desc.height_px, pic_container
        )

        shapes: list[str] = []
        sid = ctx.next_shape_id
        shapes.append(_pic_xml(sid, f"img-{asset_id[:8]}", rid, effective_box, src_rect, alt))
        sid += 1

        if caption:
            shapes.append(
                text_box(
                    sid,
                    "img-caption",
                    container.x + 160000,
                    container.y + container.h - caption_h,
                    container.w - 320000,
                    caption_h,
                    caption,
                    size_pt=10,
                    color=ctx.palette.dark,
                    align="ctr",
                    font=ctx.font,
                )
            )
            sid += 1

        return RenderOutput(shapes_xml=shapes, next_shape_id=sid)

    def _render_stub(
        self,
        asset_id: str,
        caption: str,
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        p = ctx.palette
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
