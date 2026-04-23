from __future__ import annotations

import logging

import pytest

from render.shapes import (
    DEFAULT_PALETTE,
    _contrast_ratio,
    _darken,
    _hex_to_hsl,
    _hsl_to_hex,
    _lighten,
    palette_from_theme,
)
from render.theme_loader import Theme, ThemeColors, ThemeFonts


def _fonts() -> ThemeFonts:
    return ThemeFonts(
        major_latin="",
        major_ea="",
        major_cs="",
        minor_latin="",
        minor_ea="",
        minor_cs="",
    )


def _colors(
    *,
    dk1: str = "3A3A42",
    lt1: str = "FFFFFF",
    dk2: str = "5E5C6A",
    lt2: str = "E8E6EC",
    accent1: str = "8B7AB8",
    accent2: str = "C4A05C",
    accent3: str = "5E9B7F",
    accent4: str = "FFFFFF",
    accent5: str = "FFFFFF",
    accent6: str = "FFFFFF",
    hlink: str = "0000EE",
    fol_hlink: str = "551A8B",
) -> ThemeColors:
    return ThemeColors(
        dk1=dk1,
        lt1=lt1,
        dk2=dk2,
        lt2=lt2,
        accent1=accent1,
        accent2=accent2,
        accent3=accent3,
        accent4=accent4,
        accent5=accent5,
        accent6=accent6,
        hlink=hlink,
        fol_hlink=fol_hlink,
    )


def test_default_theme_matches_default_palette_byte_for_byte() -> None:
    theme = Theme(colors=_colors(), fonts=_fonts())
    pal = palette_from_theme(theme)
    assert pal == DEFAULT_PALETTE


def test_red_accent1_produces_expected_purple_slots() -> None:
    theme = Theme(colors=_colors(accent1="FF0000"), fonts=_fonts())
    pal = palette_from_theme(theme)
    assert pal.purple == "FF0000"
    _, _, base_l = _hex_to_hsl("FF0000")
    _, _, lt_l = _hex_to_hsl(pal.purple_lt)
    _, _, dk_l = _hex_to_hsl(pal.purple_dk)
    assert lt_l > base_l
    assert dk_l < base_l


def test_lighten_zero_is_identity() -> None:
    assert _lighten("8B7AB8", 0.0) == "8B7AB8"
    assert _lighten("ff0000", 0.0) == "FF0000"


def test_darken_zero_is_identity() -> None:
    assert _darken("8B7AB8", 0.0) == "8B7AB8"
    assert _darken("abcdef", 0.0) == "ABCDEF"


def test_lighten_bounds() -> None:
    assert _lighten("000000", 1.0) == "FFFFFF"
    assert _lighten("FFFFFF", 0.5) == "FFFFFF"


def test_darken_bounds() -> None:
    assert _darken("FFFFFF", 1.0) == "000000"
    assert _darken("000000", 0.5) == "000000"


@pytest.mark.parametrize(
    "hex6",
    ["000000", "FFFFFF", "8B7AB8", "3A3A42", "C4A05C", "5E9B7F", "E8E6EC", "123456"],
)
def test_hex_hsl_round_trip(hex6: str) -> None:
    hsl = _hex_to_hsl(hex6)
    back = _hsl_to_hex(hsl)
    for i in range(0, 6, 2):
        orig = int(hex6[i : i + 2], 16)
        out = int(back[i : i + 2], 16)
        assert abs(orig - out) <= 1


def test_contrast_ratio_black_on_white_is_21() -> None:
    assert abs(_contrast_ratio("000000", "FFFFFF") - 21.0) < 0.01


def test_contrast_ratio_same_color_is_1() -> None:
    assert abs(_contrast_ratio("8B7AB8", "8B7AB8") - 1.0) < 0.001
    assert abs(_contrast_ratio("FFFFFF", "FFFFFF") - 1.0) < 0.001


def test_contrast_ratio_is_symmetric() -> None:
    assert _contrast_ratio("000000", "FFFFFF") == _contrast_ratio("FFFFFF", "000000")


def test_invalid_accent1_falls_back_to_default(caplog: pytest.LogCaptureFixture) -> None:
    theme = Theme(colors=_colors(accent1=""), fonts=_fonts())
    with caplog.at_level(logging.WARNING, logger="render.shapes"):
        pal = palette_from_theme(theme)
    assert pal.purple == DEFAULT_PALETTE.purple
    assert any("accent1" in rec.message for rec in caplog.records)


def test_invalid_dk1_falls_back(caplog: pytest.LogCaptureFixture) -> None:
    theme = Theme(colors=_colors(dk1="ZZZ"), fonts=_fonts())
    with caplog.at_level(logging.WARNING, logger="render.shapes"):
        pal = palette_from_theme(theme)
    assert pal.black == DEFAULT_PALETTE.black
    assert any("dk1" in rec.message for rec in caplog.records)


def test_invalid_multiple_slots_do_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    theme = Theme(
        colors=_colors(accent1="", dk1="", lt2="notahex", accent2="xyzxyz"),
        fonts=_fonts(),
    )
    with caplog.at_level(logging.WARNING, logger="render.shapes"):
        pal = palette_from_theme(theme)
    assert pal.purple == DEFAULT_PALETTE.purple
    assert pal.black == DEFAULT_PALETTE.black
    assert pal.border == DEFAULT_PALETTE.border
    assert pal.amber == DEFAULT_PALETTE.amber
