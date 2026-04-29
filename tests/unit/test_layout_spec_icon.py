"""Integration test: IconShape → emit_layout_spec → MediaRegistry."""

from __future__ import annotations

import pytest

from render.layout_spec import (
    IconShape,
    LayoutSpec,
    RectShape,
    emit_layout_spec,
)
from render.media import MediaRegistry
from render.shapes import DEFAULT_PALETTE


def test_icon_shape_validates() -> None:
    # Pydantic schema enforces required icon name.
    s = IconShape(x=0, y=0, w=100000, h=100000, icon="shield")
    assert s.icon == "shield"
    assert s.color == "primary"  # default token


def test_icon_shape_falls_back_to_rect_when_no_media() -> None:
    spec = LayoutSpec(
        slide_index=1,
        shapes=[
            IconShape(x=0, y=0, w=100000, h=100000, icon="shield", color="primary"),
        ],
    )
    fragments, _ = emit_layout_spec(spec, palette=DEFAULT_PALETTE, media=None)
    # No media → rect stub. This keeps emit_shape callable from unit
    # tests that don't care about the picture pipeline.
    assert fragments[0].startswith("<p:sp>"), fragments[0][:80]


def test_icon_shape_unknown_name_falls_back_gracefully() -> None:
    spec = LayoutSpec(
        slide_index=1,
        shapes=[
            IconShape(x=0, y=0, w=100000, h=100000, icon="not-a-real-icon-xyz"),
            RectShape(x=200000, y=0, w=100000, h=100000),
        ],
    )
    media = MediaRegistry()
    fragments, _ = emit_layout_spec(spec, palette=DEFAULT_PALETTE, media=media)
    # Bad icon → rect stub; sibling rect still renders. No exception
    # propagates so one bad LLM emission can't kill the slide.
    assert len(fragments) == 2
    assert fragments[0].startswith("<p:sp>")  # stub
    assert fragments[1].startswith("<p:sp>")  # rect


# The remaining tests require cairosvg to actually rasterize.
cairosvg = pytest.importorskip("cairosvg", reason="cairosvg not installed")


def test_icon_shape_emits_pic_and_registers_media() -> None:
    spec = LayoutSpec(
        slide_index=3,
        shapes=[
            IconShape(
                x=10000, y=10000, w=200000, h=200000,
                icon="trending-up", color="primary_dark",
            ),
        ],
    )
    media = MediaRegistry()
    fragments, _next_id = emit_layout_spec(spec, palette=DEFAULT_PALETTE, media=media)
    assert len(fragments) == 1
    # icon_pic emits <p:pic>, the rect-stub fallback would emit <p:sp>.
    assert fragments[0].startswith("<p:pic>"), fragments[0][:80]
    # The rasterized PNG should have been registered against slide 3.
    assert len(media.entries) == 1
    asset_id = next(iter(media.entries))
    assert asset_id.startswith("icon-trending-up-")
    assert media.entries[asset_id].inline_bytes is not None
    assert media.slide_usages == {3: {"rId10000"}}


def test_icon_shape_dedupes_same_icon_color() -> None:
    spec = LayoutSpec(
        slide_index=1,
        shapes=[
            IconShape(x=0, y=0, w=100000, h=100000, icon="shield", color="primary"),
            IconShape(x=200000, y=0, w=100000, h=100000, icon="shield", color="primary"),
            IconShape(x=400000, y=0, w=100000, h=100000, icon="shield", color="primary_dark"),
        ],
    )
    media = MediaRegistry()
    emit_layout_spec(spec, palette=DEFAULT_PALETTE, media=media)
    # Two distinct (icon, color) pairs → two entries (the two primary
    # "shield"s collapse to one).
    assert len(media.entries) == 2
