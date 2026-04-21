"""
Shape and text XML builders for PPTX generation.

Adapted from PoC scripts/shape_lib.py. All EMU values are forced to integers
at the boundary (_i) because PowerPoint rejects float EMU values even though
LibreOffice accepts them silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

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
    purple_lt: str = "D9D1E8"
    purple_dk: str = "6B5C96"
    purple_bg: str = "F5F2F9"
    black: str = "3A3A42"
    dark: str = "5E5C6A"
    muted: str = "9B98A6"
    border: str = "E8E6EC"
    bg_alt: str = "FAFAFB"
    amber: str = "C4A05C"
    green: str = "5E9B7F"


DEFAULT_PALETTE = Palette()
DEFAULT_FONT = "Noto Sans JP"


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
