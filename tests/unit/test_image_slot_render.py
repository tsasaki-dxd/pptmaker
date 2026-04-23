"""Tests for ImageSlotRenderer: unresolved stub, resolved <p:pic>, fit modes."""

from __future__ import annotations

import logging
import re

from render.figure_renderers import renderer_for
from render.figure_renderers.base import EMUBox, RenderContext
from render.media import ImageAssetDescriptor, MediaRegistry
from render.shapes import DEFAULT_FONT, DEFAULT_PALETTE

_SRC_RECT_RE = re.compile(
    r'<a:srcRect\s+l="(-?\d+)"\s+t="(-?\d+)"\s+r="(-?\d+)"\s+b="(-?\d+)"\s*/>'
)


def _box() -> EMUBox:
    return EMUBox(x=0, y=0, w=10_000_000, h=5_000_000)


def _ctx(media: MediaRegistry | None = None, slide_index: int | None = None) -> RenderContext:
    return RenderContext(
        palette=DEFAULT_PALETTE,
        font=DEFAULT_FONT,
        next_shape_id=100,
        media=media,
        slide_index=slide_index,
    )


def _desc(aid: str, w: int | None, h: int | None, mime: str = "image/png") -> ImageAssetDescriptor:
    return ImageAssetDescriptor(
        asset_id=aid, s3_key=f"assets/{aid}.png", mime=mime, width_px=w, height_px=h
    )


def test_unresolved_asset_falls_back_to_stub_with_warning(caplog) -> None:
    r = renderer_for("image_slot")
    content = {"asset_id": "abcdef1234567890", "caption": "Cap"}
    with caplog.at_level(logging.WARNING, logger="slideforge.render.image_slot"):
        out = r.render(content, _box(), _ctx(media=None))
    assert any("画像未解決" in rec.getMessage() for rec in caplog.records)
    assert any("abcdef12" in rec.getMessage() for rec in caplog.records)
    xml_joined = "".join(out.shapes_xml)
    assert "<p:pic>" not in xml_joined
    assert "<p:sp>" in xml_joined


def test_resolved_but_not_in_resolved_dict_falls_back(caplog) -> None:
    r = renderer_for("image_slot")
    media = MediaRegistry()
    with caplog.at_level(logging.WARNING, logger="slideforge.render.image_slot"):
        out = r.render({"asset_id": "zzz"}, _box(), _ctx(media=media))
    assert any("画像未解決" in rec.getMessage() for rec in caplog.records)
    xml_joined = "".join(out.shapes_xml)
    assert "<p:pic>" not in xml_joined


def test_resolved_cover_wide_image_produces_horizontal_srcrect() -> None:
    # container 10_000_000 x 5_000_000 -> aspect 2.0
    # image 4000 x 1000 -> aspect 4.0, wider than container -> crop left/right
    r = renderer_for("image_slot")
    media = MediaRegistry()
    desc = _desc("wide", 4000, 1000)
    media.resolved[desc.asset_id] = desc
    out = r.render(
        {"asset_id": "wide", "fit": "cover"}, _box(), _ctx(media=media, slide_index=1)
    )
    xml_joined = "".join(out.shapes_xml)
    assert "<p:pic>" in xml_joined
    m = _SRC_RECT_RE.search(xml_joined)
    assert m is not None, f"srcRect not found in: {xml_joined}"
    left, top, right, bot = (int(g) for g in m.groups())
    assert top == 0 and bot == 0
    assert left == right
    # 4000 wide, container ar 2.0 -> crop to width 2000, l = 1000/4000 = 25% = 25000
    assert left == 25000


def test_resolved_cover_tall_image_produces_vertical_srcrect() -> None:
    # container 10_000_000 x 5_000_000 -> aspect 2.0
    # image 1000 x 1000 -> aspect 1.0 < 2.0 -> crop top/bottom
    r = renderer_for("image_slot")
    media = MediaRegistry()
    desc = _desc("tall", 1000, 1000)
    media.resolved[desc.asset_id] = desc
    out = r.render(
        {"asset_id": "tall", "fit": "cover"}, _box(), _ctx(media=media, slide_index=2)
    )
    xml_joined = "".join(out.shapes_xml)
    m = _SRC_RECT_RE.search(xml_joined)
    assert m is not None
    left, top, right, bot = (int(g) for g in m.groups())
    assert left == 0 and right == 0
    assert top == bot
    # container ar 2.0, image ar 1.0 -> crop_h = 1000/2.0 = 500, t = 250/1000 = 25%
    assert top == 25000


def test_resolved_contain_shrinks_container() -> None:
    # wide image in 2:1 container with image ar 4:1 => shrink height
    r = renderer_for("image_slot")
    media = MediaRegistry()
    desc = _desc("c", 4000, 1000)
    media.resolved[desc.asset_id] = desc
    out = r.render(
        {"asset_id": "c", "fit": "contain"}, _box(), _ctx(media=media, slide_index=1)
    )
    xml_joined = "".join(out.shapes_xml)
    assert "<p:pic>" in xml_joined
    assert _SRC_RECT_RE.search(xml_joined) is None
    m_ext = re.search(r'<a:ext\s+cx="(\d+)"\s+cy="(\d+)"', xml_joined)
    assert m_ext is not None
    cx, cy = int(m_ext.group(1)), int(m_ext.group(2))
    # cx should stay at 10_000_000, cy should be 10_000_000 / 4 = 2_500_000
    assert cx == 10_000_000
    assert cy == 2_500_000


def test_resolved_fill_emits_no_srcrect() -> None:
    r = renderer_for("image_slot")
    media = MediaRegistry()
    desc = _desc("f", 4000, 1000)
    media.resolved[desc.asset_id] = desc
    out = r.render(
        {"asset_id": "f", "fit": "fill"}, _box(), _ctx(media=media, slide_index=1)
    )
    xml_joined = "".join(out.shapes_xml)
    assert "<p:pic>" in xml_joined
    assert _SRC_RECT_RE.search(xml_joined) is None


def test_resolved_fit_width_scales_height_to_image_aspect() -> None:
    r = renderer_for("image_slot")
    media = MediaRegistry()
    desc = _desc("w", 4000, 1000)
    media.resolved[desc.asset_id] = desc
    out = r.render(
        {"asset_id": "w", "fit": "fit_width"}, _box(), _ctx(media=media, slide_index=1)
    )
    xml_joined = "".join(out.shapes_xml)
    assert _SRC_RECT_RE.search(xml_joined) is None
    m_ext = re.search(r'<a:ext\s+cx="(\d+)"\s+cy="(\d+)"', xml_joined)
    assert m_ext is not None
    cx, cy = int(m_ext.group(1)), int(m_ext.group(2))
    assert cx == 10_000_000
    assert cy == 2_500_000


def test_resolved_registers_rid_with_media() -> None:
    r = renderer_for("image_slot")
    media = MediaRegistry()
    desc = _desc("r", 1000, 1000)
    media.resolved[desc.asset_id] = desc
    out = r.render({"asset_id": "r"}, _box(), _ctx(media=media, slide_index=3))
    xml_joined = "".join(out.shapes_xml)
    assert 'r:embed="rId10000"' in xml_joined
    assert media.slide_usages[3] == {"rId10000"}
