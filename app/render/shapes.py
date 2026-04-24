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


def _run(
    text: str,
    size_pt: int,
    bold: bool,
    color: str,
    font: str,
    *,
    italic: bool = False,
    underline: bool = False,
) -> str:
    b = "1" if bold else "0"
    i_attr = ' i="1"' if italic else ""
    u_attr = ' u="sng"' if underline else ""
    return (
        f'<a:r><a:rPr lang="ja-JP" sz="{size_pt * 100}" b="{b}"{i_attr}{u_attr}>'
        f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        f'<a:latin typeface="{font}"/>'
        f'<a:ea typeface="{font}"/>'
        f"</a:rPr>"
        f"<a:t>{_xml_escape(text)}</a:t></a:r>"
    )


@dataclass(frozen=True)
class TextRun:
    """One styled text run inside a paragraph."""

    text: str
    size_pt: int = 11
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str = "111111"


@dataclass(frozen=True)
class TextParagraph:
    """One paragraph (logical line / bullet) inside a text frame.

    `bullet` controls the leading marker:
      * None   → no bullet, plain paragraph
      * "•"    → unicode bullet character (or any single-char string)
      * "1."   → arabic-period auto-numbering (continues across paragraphs)
    `indent_level` (0–8) controls left margin / nesting; renderer uses
    285750 EMU per level (PowerPoint's default).
    `line_spacing_pct` is 100 = single, 150 = 1.5×, etc.
    `align` matches PPTX values: "l" / "ctr" / "r" / "just".
    """

    runs: tuple[TextRun, ...] = ()
    align: str = "l"
    indent_level: int = 0
    bullet: str | None = None
    line_spacing_pct: int = 100
    space_before_pt: int = 0
    space_after_pt: int = 0


def _render_paragraph(p: TextParagraph, font: str) -> str:
    ppr_attrs: list[str] = [f'algn="{p.align}"']
    if p.indent_level > 0:
        ppr_attrs.append(f'marL="{285750 * p.indent_level}"')
        ppr_attrs.append(f'lvl="{p.indent_level}"')
    if p.bullet:
        # Hanging indent so wrapped lines align under the text, not the bullet.
        if p.indent_level == 0:
            ppr_attrs.append('marL="285750"')
        ppr_attrs.append('indent="-285750"')

    children: list[str] = []
    if p.line_spacing_pct != 100:
        children.append(f'<a:lnSpc><a:spcPct val="{p.line_spacing_pct * 1000}"/></a:lnSpc>')
    if p.space_before_pt:
        children.append(f'<a:spcBef><a:spcPts val="{p.space_before_pt * 100}"/></a:spcBef>')
    if p.space_after_pt:
        children.append(f'<a:spcAft><a:spcPts val="{p.space_after_pt * 100}"/></a:spcAft>')
    if p.bullet:
        if p.bullet.endswith(".") and p.bullet.rstrip(".").isdigit():
            children.append('<a:buAutoNum type="arabicPeriod"/>')
        else:
            children.append(f'<a:buChar char="{_xml_escape(p.bullet)}"/>')

    if children:
        ppr = f'<a:pPr {" ".join(ppr_attrs)}>{"".join(children)}</a:pPr>'
    else:
        ppr = f'<a:pPr {" ".join(ppr_attrs)}/>'

    runs_xml = "".join(
        _run(
            r.text,
            r.size_pt,
            r.bold,
            r.color,
            font,
            italic=r.italic,
            underline=r.underline,
        )
        for r in p.runs
    )
    return f"<a:p>{ppr}{runs_xml}</a:p>"


def text_box_paragraphs(
    sp_id: int,
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    paragraphs: list[TextParagraph] | tuple[TextParagraph, ...],
    *,
    font: str = DEFAULT_FONT,
    anchor: str = "t",
    auto_fit: bool = False,
) -> str:
    """Multi-paragraph text box.

    Each TextParagraph maps to one `<a:p>` so line breaks, bullet
    markers, indent levels, line spacing and per-paragraph alignment
    work the way PowerPoint expects. `anchor` is vertical alignment
    ("t" / "ctr" / "b") inside the shape.
    """
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    body = "".join(_render_paragraph(p, font) for p in paragraphs)
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        f"<p:spPr>"
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f"<a:noFill/>"
        f"</p:spPr>"
        f"<p:txBody>{_body_pr(auto_fit, anchor)}<a:lstStyle/>"
        f"{body}"
        f"</p:txBody>"
        f"</p:sp>"
    )


def round_rect_shape(
    sp_id: int,
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    fill_color: str,
    *,
    corner_radius_pct: int = 25,
    line_color: str | None = None,
    line_width_emu: int = 0,
) -> str:
    """Filled rectangle with custom rounded corners.

    `corner_radius_pct` 0..50: 0 → sharp corners (equivalent to
    rect_shape), 50 → fully rounded (a square becomes a circle, a
    horizontal rectangle becomes a pill). Values map to OOXML's
    `roundRect` adj range 0..50000 (1000ths of a percent of half the
    shorter side).
    """
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    radius = max(0, min(50, int(corner_radius_pct)))
    av_lst = f'<a:gd name="adj" fmla="val {radius * 1000}"/>'
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
        f"<p:spPr>"
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="roundRect"><a:avLst>{av_lst}</a:avLst></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill_color}"/></a:solidFill>'
        f"{ln}"
        f"</p:spPr>"
        f'<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>'
        f"</p:sp>"
    )


def resolve_palette_color(token: str, palette: Palette | None = None) -> str:
    """Accept either a 6-char HEX color (returned uppercase) or a
    palette field name ("purple" / "muted" / "amber" / etc.) and
    return the resolved HEX. Lets LLM specs use semantic color names
    instead of pinning HEXes that should follow the active theme.
    Unknown tokens fall back to the palette's `purple`.
    """
    s = token.strip()
    if len(s) == 6 and all(c in "0123456789abcdefABCDEF" for c in s):
        return s.upper()
    if s.startswith("#") and len(s) == 7:
        return s[1:].upper()
    pal = palette or DEFAULT_PALETTE
    return getattr(pal, s, pal.purple)


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def fit_stack(
    container_h: int,
    n: int,
    *,
    natural_h: int,
    min_h: int,
    gap: int = 0,
    min_gap: int = 0,
    header_h: int = 0,
    footer_h: int = 0,
) -> tuple[int, int]:
    """Compute ``(item_h, gap)`` for an N-item vertical stack that fits
    inside ``container_h`` after reserving ``header_h`` + ``footer_h``.

    Algorithm:
      1. Try the natural sizes; if the stack already fits, return them.
      2. Shrink the gap toward ``min_gap`` first (keeps elements at their
         natural height; only the breathing room collapses).
      3. If still too tall, shrink ``item_h`` toward ``min_h``,
         distributing the remaining vertical space evenly among items.
      4. Floor at ``(min_h, min_gap)`` — caller decides whether to drop
         items, switch layout, or accept a tight render. The PoC pattern
         for slide15 (bar_h 0.4→0.32, gap 0.12→0.08) is exactly this:
         shrink gap, then height, until the stack fits.

    `n=0` returns `(0, 0)`. `n=1` ignores `gap` and clamps the single
    item to the available height (capped at `natural_h`).
    """
    if n <= 0:
        return (0, 0)

    available = max(0, container_h - header_h - footer_h)
    if available <= 0:
        return (max(min_h, 0), max(min_gap, 0))

    if n == 1:
        item_h = min(natural_h, available)
        return (max(min_h, item_h), 0)

    natural_total = n * natural_h + (n - 1) * gap
    if natural_total <= available:
        return (natural_h, gap)

    # Step 1: collapse gap toward min_gap before touching item heights.
    reduced_total = n * natural_h + (n - 1) * min_gap
    if reduced_total <= available:
        return (natural_h, min_gap)

    # Step 2: distribute the remaining height evenly into items.
    item_h = (available - (n - 1) * min_gap) // n
    item_h = max(min_h, item_h)
    return (item_h, min_gap)


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


def _body_pr(auto_fit: bool, anchor: str = "t") -> str:
    """Render the <a:bodyPr> tag, optionally with normAutofit so
    PowerPoint shrinks the text to fit the shape when overflow would
    otherwise clip it. PoC slides hand-tuned font sizes to avoid clip;
    this is the productized safety net for renderers that opt in.
    """
    if auto_fit:
        return f'<a:bodyPr wrap="square" anchor="{anchor}"><a:normAutofit/></a:bodyPr>'
    return f'<a:bodyPr wrap="square" anchor="{anchor}"/>'


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
    auto_fit: bool = False,
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
        f"<p:txBody>{_body_pr(auto_fit)}<a:lstStyle/>"
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
    auto_fit: bool = False,
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
        f"<p:txBody>{_body_pr(auto_fit)}<a:lstStyle/>"
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
