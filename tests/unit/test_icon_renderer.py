"""Tests for the SVG icon rasterizer."""

from __future__ import annotations

import pytest

from render.icon_renderer import (
    ICON_CATALOG,
    asset_id_for,
    is_known,
    render_icon_png,
)

# Skip the rasterization tests if cairosvg isn't installed (the
# render-side requirements include it; tests/api venvs may not).
cairosvg = pytest.importorskip("cairosvg", reason="cairosvg not installed")


def test_catalog_populated() -> None:
    # Sanity: bundled Lucide icons should be discoverable.
    assert len(ICON_CATALOG) >= 50
    assert is_known("trending-up")
    assert is_known("shield")
    assert not is_known("not-a-real-icon-xyz")


def test_asset_id_stable_across_color_case() -> None:
    # Same icon + same color (regardless of '#' / case) yields one
    # asset_id so the MediaRegistry only embeds the PNG once.
    a = asset_id_for("trending-up", "#6A55A0")
    b = asset_id_for("trending-up", "6a55a0")
    assert a == b == "icon-trending-up-6a55a0"


def test_asset_id_differs_per_color() -> None:
    a = asset_id_for("trending-up", "6A55A0")
    b = asset_id_for("trending-up", "FFFFFF")
    assert a != b


def test_render_returns_png_bytes() -> None:
    png = render_icon_png("trending-up", "#6A55A0", size_px=64)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 100  # not a degenerate empty PNG


def test_render_lru_cached() -> None:
    # Same args → same bytes object back (LRU cache identity).
    a = render_icon_png("trending-up", "#6A55A0", size_px=64)
    b = render_icon_png("trending-up", "#6A55A0", size_px=64)
    assert a is b


def test_render_unknown_icon_raises() -> None:
    with pytest.raises(ValueError, match="unknown icon"):
        render_icon_png("not-a-real-icon-xyz", "#000000")


def test_render_invalid_color_raises() -> None:
    with pytest.raises(ValueError, match="6-char HEX"):
        render_icon_png("trending-up", "purple")
