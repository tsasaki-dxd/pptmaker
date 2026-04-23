"""
Shape and text XML builders for PPTX generation.

Adapted from PoC scripts/shape_lib.py. All EMU values are forced to integers
at the boundary (_i) because PowerPoint rejects float EMU values even though
LibreOffice accepts them silently.
"""

from __future__ import annotations

import colorsys
import logging
from dataclasses import dataclass, fields
from typing import Final

from render.theme_loader import Theme

_log = logging.getLogger(__name__)

EMU_PER_INCH: Final[int] = 914400


def inch(v: float) -> int:
    """Convert inches to integer EMU."""
    return round(v * EMU_PER_INCH)


def _i(v: float) -> int:
    """Integer guard for EMU values (PowerPoint compatibility)."""
    return round(v)


@dataclass(frozen=True)
class Palette:
    """Color palette (hex without #)."""

    purple: str = "8B7AB8"
    purple_lt: str = "B9AFD4"
    purple_dk: str = "6A55A0"
    purple_bg: str = "EEEBF4"
    black: str = "3A3A42"
    dark: str = "5E5C6A"
    muted: str = "9B9BA2"
    border: str = "E8E6EC"
    bg_alt: str = "FFFFFF"
    amber: str = "C4A05C"
    green: str = "5E9B7F"


DEFAULT_PALETTE = Palette()
DEFAULT_FONT = "Noto Sans JP"


def _is_valid_hex6(s: object) -> bool:
    if not isinstance(s, str) or len(s) != 6:
        return False
    try:
        int(s, 16)
    except ValueError:
        return False
    return True


def _hex_to_hsl(h: str) -> tuple[float, float, float]:
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    return (hue, sat, light)


def _hsl_to_hex(hsl: tuple[float, float, float]) -> str:
    hue, sat, light = hsl
    light = max(0.0, min(1.0, light))
    sat = max(0.0, min(1.0, sat))
    r, g, b = colorsys.hls_to_rgb(hue, light, sat)
    return f"{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"


def _lighten(hex6: str, amount: float) -> str:
    hue, sat, light = _hex_to_hsl(hex6)
    new_l = light + (1.0 - light) * amount
    return _hsl_to_hex((hue, sat, new_l))


def _darken(hex6: str, amount: float) -> str:
    hue, sat, light = _hex_to_hsl(hex6)
    new_l = light * (1.0 - amount)
    return _hsl_to_hex((hue, sat, new_l))


def _midpoint_hsl(a: str, b: str) -> str:
    a_h, a_s, a_l = _hex_to_hsl(a)
    _, b_s, b_l = _hex_to_hsl(b)
    return _hsl_to_hex((a_h, (a_s + b_s) / 2.0, (a_l + b_l) / 2.0))


def _relative_luminance(hex6: str) -> float:
    r = int(hex6[0:2], 16) / 255.0
    g = int(hex6[2:4], 16) / 255.0
    b = int(hex6[4:6], 16) / 255.0

    def _ch(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _ch(r) + 0.7152 * _ch(g) + 0.0722 * _ch(b)


def _contrast_ratio(fg: str, bg: str) -> float:
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter, darker = (l1, l2) if l1 >= l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


def _pick(raw: object, default: str, slot_name: str) -> str:
    if _is_valid_hex6(raw):
        return raw.upper()  # type: ignore[union-attr]
    _log.warning("palette_from_theme: invalid %s=%r, using default %s", slot_name, raw, default)
    return default


def palette_from_theme(theme: Theme) -> Palette:
    c = theme.colors
    defaults = {f.name: f.default for f in fields(Palette)}

    accent1 = _pick(c.accent1, defaults["purple"], "accent1")
    dk1 = _pick(c.dk1, defaults["black"], "dk1")
    dk2 = _pick(c.dk2, defaults["dark"], "dark")
    lt1 = _pick(c.lt1, "FFFFFF", "lt1")
    lt2 = _pick(c.lt2, defaults["border"], "lt2")
    accent2 = _pick(c.accent2, defaults["amber"], "accent2")
    accent3 = _pick(c.accent3, defaults["green"], "accent3")

    return Palette(
        purple=accent1,
        purple_lt=_lighten(accent1, 0.40),
        purple_dk=_darken(accent1, 0.20),
        purple_bg=_lighten(accent1, 0.85),
        black=dk1,
        dark=dk2,
        muted=_midpoint_hsl(dk1, lt1),
        border=lt2,
        bg_alt=_lighten(lt1, 0.05),
        amber=accent2,
        green=accent3,
    )


def _run(text: str, size_pt: int, bold: bool, color: str, font: str) -> str:
    b = "1" if bold else "0"
    return (
        f'<a:r><a:rPr lang="ja-JP" sz="{size_pt * 100}" b="{b}">'
        f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        f'<a:latin typeface="{font}"/>'
        f'<a:ea typeface="{font}"/>'
        f"</a:rPr>"
        f"<a:t>{_xml_escape(text)}</a:t></a:r>"
    )


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def rect_shape(
    sp_id: int,
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    fill_color: str,
    line_color: str | None = None,
    line_width_emu: int = 0,
) -> str:
    """Filled rectangle shape (EMU-safe)."""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    ln = ""
    if line_color:
        ln = (
            f'<a:ln w="{_i(line_width_emu)}">'
            f'<a:solidFill><a:srgbClr val="{line_color}"/></a:solidFill>'
            f"</a:ln>"
        )
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f'<p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill_color}"/></a:solidFill>'
        f"{ln}"
        f"</p:spPr>"
        f"<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>"
        f"</p:sp>"
    )


def rect_outline(
    sp_id: int,
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    line_color: str,
    line_width_emu: int = 6350,
) -> str:
    """Outline-only rectangle."""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f'<p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:noFill/>'
        f'<a:ln w="{_i(line_width_emu)}"><a:solidFill><a:srgbClr val="{line_color}"/></a:solidFill></a:ln>'
        f"</p:spPr>"
        f"<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>"
        f"</p:sp>"
    )


def text_box(
    sp_id: int,
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    size_pt: int = 11,
    bold: bool = False,
    color: str = DEFAULT_PALETTE.black,
    font: str = DEFAULT_FONT,
    align: str = "l",
) -> str:
    """Single-run text box."""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f"<a:noFill/>"
        f"</p:spPr>"
        f'<p:txBody><a:bodyPr wrap="square" anchor="t"/><a:lstStyle/>'
        f'<a:p><a:pPr algn="{align}"/>'
        f"{_run(text, size_pt, bold, color, font)}"
        f"</a:p></p:txBody>"
        f"</p:sp>"
    )


def text_box_multi(
    sp_id: int,
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    runs: list[tuple[str, int, bool, str]],
    font: str = DEFAULT_FONT,
    align: str = "l",
) -> str:
    """Multi-run text box. runs: list of (text, size_pt, bold, color)."""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    body_runs = "".join(_run(t, sz, b, c, font) for t, sz, b, c in runs)
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f"<a:noFill/>"
        f"</p:spPr>"
        f'<p:txBody><a:bodyPr wrap="square" anchor="t"/><a:lstStyle/>'
        f'<a:p><a:pPr algn="{align}"/>'
        f"{body_runs}"
        f"</a:p></p:txBody>"
        f"</p:sp>"
    )


def pill_label(
    sp_id: int,
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    fill_color: str,
    text_color: str = "FFFFFF",
    size_pt: int = 9,
    font: str = DEFAULT_FONT,
) -> str:
    """Pill-shaped label (rounded rectangle)."""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f'<p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val 50000"/></a:avLst></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill_color}"/></a:solidFill>'
        f"</p:spPr>"
        f'<p:txBody><a:bodyPr wrap="square" anchor="ctr" anchorCtr="1"/><a:lstStyle/>'
        f'<a:p><a:pPr algn="ctr"/>'
        f"{_run(text, size_pt, True, text_color, font)}"
        f"</a:p></p:txBody>"
        f"</p:sp>"
    )


def h_line(
    sp_id: int,
    name: str,
    x: float,
    y: float,
    w: float,
    color: str,
    width_emu: int = 9525,
) -> str:
    """Horizontal line (thin rectangle)."""
    x, y, w = _i(x), _i(y), _i(w)
    h = _i(width_emu)
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f'<p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        f"</p:spPr>"
        f"<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>"
        f"</p:sp>"
    )
