from __future__ import annotations

import io
import zipfile

import pytest

from render.theme_loader import ThemeParseError, load_theme, parse_theme_xml

_NS = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'


def _theme(clr_scheme_inner: str, font_scheme_inner: str) -> bytes:
    xml = (
        f'<a:theme {_NS} name="t">'
        "<a:themeElements>"
        f'<a:clrScheme name="c">{clr_scheme_inner}</a:clrScheme>'
        f'<a:fontScheme name="f">{font_scheme_inner}</a:fontScheme>'
        "</a:themeElements>"
        "</a:theme>"
    )
    return xml.encode("utf-8")


def _srgb(slot: str, hex_val: str) -> str:
    return f'<a:{slot}><a:srgbClr val="{hex_val}"/></a:{slot}>'


def _full_color_scheme() -> str:
    mapping = {
        "dk1": "111111",
        "lt1": "FFFFFF",
        "dk2": "222222",
        "lt2": "EEEEEE",
        "accent1": "AA1111",
        "accent2": "AA2222",
        "accent3": "AA3333",
        "accent4": "AA4444",
        "accent5": "AA5555",
        "accent6": "AA6666",
        "hlink": "0000EE",
        "folHlink": "551A8B",
    }
    return "".join(_srgb(k, v) for k, v in mapping.items())


def _full_font_scheme() -> str:
    return (
        "<a:majorFont>"
        '<a:latin typeface="Calibri Light"/>'
        '<a:ea typeface="Yu Gothic"/>'
        '<a:cs typeface="Arial"/>'
        "</a:majorFont>"
        "<a:minorFont>"
        '<a:latin typeface="Calibri"/>'
        '<a:ea typeface="Meiryo"/>'
        '<a:cs typeface="Arial"/>'
        "</a:minorFont>"
    )


def test_parse_all_srgb() -> None:
    theme = parse_theme_xml(_theme(_full_color_scheme(), _full_font_scheme()))
    c = theme.colors
    assert c.dk1 == "111111"
    assert c.lt1 == "FFFFFF"
    assert c.dk2 == "222222"
    assert c.lt2 == "EEEEEE"
    assert c.accent1 == "AA1111"
    assert c.accent6 == "AA6666"
    assert c.hlink == "0000EE"
    assert c.fol_hlink == "551A8B"
    f = theme.fonts
    assert f.major_latin == "Calibri Light"
    assert f.major_ea == "Yu Gothic"
    assert f.major_cs == "Arial"
    assert f.minor_latin == "Calibri"
    assert f.minor_ea == "Meiryo"
    assert f.minor_cs == "Arial"


def test_parse_sysclr_lastclr_fallback() -> None:
    scheme = (
        '<a:dk1><a:sysClr val="windowText" lastClr="123456"/></a:dk1>'
        '<a:lt1><a:sysClr val="window" lastClr="abcdef"/></a:lt1>'
        + _srgb("dk2", "222222")
        + _srgb("lt2", "EEEEEE")
        + _srgb("accent1", "AA1111")
        + _srgb("accent2", "AA2222")
        + _srgb("accent3", "AA3333")
        + _srgb("accent4", "AA4444")
        + _srgb("accent5", "AA5555")
        + _srgb("accent6", "AA6666")
        + _srgb("hlink", "0000EE")
        + _srgb("folHlink", "551A8B")
    )
    theme = parse_theme_xml(_theme(scheme, _full_font_scheme()))
    assert theme.colors.dk1 == "123456"
    assert theme.colors.lt1 == "ABCDEF"


def test_missing_accents_default() -> None:
    scheme = (
        _srgb("dk1", "111111")
        + _srgb("lt1", "FFFFFF")
        + _srgb("dk2", "222222")
        + _srgb("lt2", "EEEEEE")
        + _srgb("accent1", "AA1111")
        + _srgb("accent2", "AA2222")
        # accent3 and accent4 missing
        + _srgb("accent5", "AA5555")
        + _srgb("accent6", "AA6666")
        + _srgb("hlink", "0000EE")
        + _srgb("folHlink", "551A8B")
    )
    theme = parse_theme_xml(_theme(scheme, _full_font_scheme()))
    assert theme.colors.accent3 == "FFFFFF"
    assert theme.colors.accent4 == "FFFFFF"
    assert theme.colors.accent1 == "AA1111"


def test_missing_major_ea_is_empty() -> None:
    font_scheme = (
        "<a:majorFont>"
        '<a:latin typeface="Calibri Light"/>'
        '<a:cs typeface="Arial"/>'
        "</a:majorFont>"
        "<a:minorFont>"
        '<a:latin typeface="Calibri"/>'
        '<a:ea typeface="Meiryo"/>'
        '<a:cs typeface="Arial"/>'
        "</a:minorFont>"
    )
    theme = parse_theme_xml(_theme(_full_color_scheme(), font_scheme))
    assert theme.fonts.major_ea == ""
    assert theme.fonts.major_latin == "Calibri Light"
    assert theme.fonts.minor_ea == "Meiryo"


def _minimal_pptx(theme_xml: bytes | None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", b"<x/>")
        if theme_xml is not None:
            zf.writestr("ppt/theme/theme1.xml", theme_xml)
    return buf.getvalue()


def test_load_theme_from_zip() -> None:
    pptx = _minimal_pptx(_theme(_full_color_scheme(), _full_font_scheme()))
    theme = load_theme(pptx)
    assert theme.colors.accent1 == "AA1111"
    assert theme.fonts.minor_ea == "Meiryo"


def test_load_theme_missing_file_raises() -> None:
    pptx = _minimal_pptx(None)
    with pytest.raises(ThemeParseError):
        load_theme(pptx)
