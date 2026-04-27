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


# Aliases the layout-designer LLM is taught to emit but which don't
# match Palette field names 1:1. Mapped here so old prompts and new
# theme-agnostic vocab both resolve sensibly.
_PALETTE_ALIASES: Final[dict[str, str]] = {
    "primary": "purple",
    "primary_dark": "purple_dk",
    "primary_lt": "purple_lt",
    "primary_bg": "purple_bg",
    "text_dark": "black",
    "text_muted": "muted",
    "accent": "amber",
}

# Tokens that resolve to a fixed HEX regardless of palette (used so
# "white" doesn't silently fall back to purple on an unknown lookup).
_FIXED_TOKENS: Final[dict[str, str]] = {
    "white": "FFFFFF",
    "none": "FFFFFF",
    "transparent": "FFFFFF",
}


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
    key = s.lower()
    if key in _FIXED_TOKENS:
        return _FIXED_TOKENS[key]
    key = _PALETTE_ALIASES.get(key, key)
    pal = palette or DEFAULT_PALETTE
    return getattr(pal, key, pal.purple)


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


# ---- Table / Chart primitives -------------------------------------------
#
# These emit composite XML (one or more <p:sp> / <p:graphicFrame> siblings)
# in a single string. Sub-shape IDs are allocated as `sp_id * 100 + i` so
# they never collide with the parent or sibling IDs that emit_layout_spec
# hands out incrementally.


def _sub_id(sp_id: int, i: int) -> int:
    return sp_id * 100 + i


def table_shape(
    sp_id: int,
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    rows: list[list[str]],
    column_weights: list[float] | None = None,
    header: bool = True,
    alt_row_bg: bool = False,
    header_fill: str = DEFAULT_PALETTE.purple,
    header_text_color: str = "FFFFFF",
    body_text_color: str = DEFAULT_PALETTE.black,
    alt_row_fill: str = DEFAULT_PALETTE.purple_bg,
    border_color: str = DEFAULT_PALETTE.border,
    font_size_pt: int = 10,
    font: str = DEFAULT_FONT,
) -> str:
    """OOXML table inside a <p:graphicFrame>.

    `rows` is a list of row lists; each cell is a plain string (no
    inline runs — keep the schema simple, matching what the LLM can
    reliably emit). When `header` is True the first row is styled as
    the header. Column widths are derived from `column_weights` (if
    given) or distributed evenly. Row heights are distributed evenly
    across `h`.
    """
    if not rows:
        # Pydantic enforces at least one row, but be defensive.
        return ""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    n_cols = max(len(r) for r in rows)
    n_rows = len(rows)

    if column_weights and len(column_weights) == n_cols and sum(column_weights) > 0:
        total = sum(column_weights)
        col_widths = [_i(w * c / total) for c in column_weights]
        # Fix any rounding drift so columns sum exactly to w.
        col_widths[-1] += w - sum(col_widths)
    else:
        base = w // n_cols
        col_widths = [base] * n_cols
        col_widths[-1] += w - base * n_cols

    row_h = h // n_rows
    row_heights = [row_h] * n_rows
    row_heights[-1] += h - row_h * n_rows

    grid = "".join(f'<a:gridCol w="{cw}"/>' for cw in col_widths)
    tbl_grid = f"<a:tblGrid>{grid}</a:tblGrid>"

    def _cell_xml(text: str, *, is_header: bool, is_alt: bool) -> str:
        if is_header:
            fill = header_fill
            tcolor = header_text_color
            bold = True
        else:
            fill = alt_row_fill if is_alt else "FFFFFF"
            tcolor = body_text_color
            bold = False
        # Borders on all four sides for legibility.
        ln = (
            f'<a:lnL w="6350"><a:solidFill><a:srgbClr val="{border_color}"/></a:solidFill></a:lnL>'
            f'<a:lnR w="6350"><a:solidFill><a:srgbClr val="{border_color}"/></a:solidFill></a:lnR>'
            f'<a:lnT w="6350"><a:solidFill><a:srgbClr val="{border_color}"/></a:solidFill></a:lnT>'
            f'<a:lnB w="6350"><a:solidFill><a:srgbClr val="{border_color}"/></a:solidFill></a:lnB>'
        )
        body = (
            f'<a:txBody><a:bodyPr wrap="square" anchor="ctr"/><a:lstStyle/>'
            f'<a:p><a:pPr algn="l"/>'
            f"{_run(text, font_size_pt, bold, tcolor, font)}"
            f"</a:p></a:txBody>"
        )
        tcpr = (
            f'<a:tcPr marL="36000" marR="36000" marT="18000" marB="18000">'
            f"{ln}"
            f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
            f"</a:tcPr>"
        )
        return f"<a:tc>{body}{tcpr}</a:tc>"

    rows_xml: list[str] = []
    for ri, row in enumerate(rows):
        cells = []
        for ci in range(n_cols):
            text = row[ci] if ci < len(row) else ""
            is_header = header and ri == 0
            is_alt = alt_row_bg and not is_header and (ri % 2 == (1 if header else 0))
            cells.append(_cell_xml(text, is_header=is_header, is_alt=is_alt))
        rows_xml.append(
            f'<a:tr h="{row_heights[ri]}">{"".join(cells)}</a:tr>'
        )

    tbl = (
        f'<a:tbl>'
        f'<a:tblPr firstRow="{1 if header else 0}" bandRow="{1 if alt_row_bg else 0}">'
        f'<a:tableStyleId>{{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}}</a:tableStyleId>'
        f"</a:tblPr>"
        f"{tbl_grid}"
        f"{''.join(rows_xml)}"
        f"</a:tbl>"
    )
    return (
        f'<p:graphicFrame>'
        f'<p:nvGraphicFramePr>'
        f'<p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f'<p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr>'
        f"<p:nvPr/>"
        f"</p:nvGraphicFramePr>"
        f'<p:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></p:xfrm>'
        f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table">'
        f"{tbl}"
        f"</a:graphicData></a:graphic>"
        f"</p:graphicFrame>"
    )


def _ellipse_marker(
    sp_id: int, name: str, cx: int, cy: int, r: int, fill: str
) -> str:
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f"<p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
        f'<p:spPr>'
        f'<a:xfrm><a:off x="{cx - r}" y="{cy - r}"/><a:ext cx="{2 * r}" cy="{2 * r}"/></a:xfrm>'
        f'<a:prstGeom prst="ellipse"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
        f"</p:spPr>"
        f"<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>"
        f"</p:sp>"
    )


def _segment_line(
    sp_id: int,
    name: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: str,
    width_emu: int = 19050,
) -> str:
    """Diagonal line implemented as <p:cxnSp> straight connector. Used
    by line_chart_shape for series segments."""
    bx, by = min(x1, x2), min(y1, y2)
    bw, bh = max(abs(x2 - x1), 1), max(abs(y2 - y1), 1)
    flip_h = "1" if x2 < x1 else "0"
    flip_v = "1" if y2 < y1 else "0"
    return (
        f'<p:cxnSp><p:nvCxnSpPr>'
        f'<p:cNvPr id="{sp_id}" name="{_xml_escape(name)}"/>'
        f"<p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr>"
        f'<p:spPr>'
        f'<a:xfrm flipH="{flip_h}" flipV="{flip_v}">'
        f'<a:off x="{bx}" y="{by}"/><a:ext cx="{bw}" cy="{bh}"/>'
        f"</a:xfrm>"
        f'<a:prstGeom prst="line"><a:avLst/></a:prstGeom>'
        f'<a:ln w="{width_emu}"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:ln>'
        f"</p:spPr>"
        f"</p:cxnSp>"
    )


def bar_chart_shape(
    sp_id: int,
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    items: list[tuple[str, float, str | None]],
    orientation: str = "v",
    show_values: bool = True,
    value_format: str = "{:g}",
    bar_color: str = DEFAULT_PALETTE.purple,
    axis_color: str = DEFAULT_PALETTE.border,
    label_color: str = DEFAULT_PALETTE.dark,
    value_color: str = DEFAULT_PALETTE.black,
    font_size_pt: int = 10,
    font: str = DEFAULT_FONT,
) -> str:
    """Composite vertical or horizontal bar chart.

    `items` is `[(label, value, color_or_None), ...]`. Negative values
    are clamped to 0 (this primitive does not support diverging axes).
    For `orientation="v"`: bars grow upward from a baseline at the
    bottom; labels under the axis; values above each bar.
    For `orientation="h"`: bars grow rightward from a left axis;
    labels left of the axis; values to the right of each bar.
    """
    if not items:
        return ""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    values = [max(0.0, float(v)) for _, v, _ in items]
    vmax = max(values) if values else 0.0
    if vmax <= 0:
        vmax = 1.0  # avoid div-by-zero; bars render as 0-height
    n = len(items)
    label_band = _i(font_size_pt * 100 * 2.5)  # ~2.5 lines
    value_band = _i(font_size_pt * 100 * 1.8) if show_values else 0
    parts: list[str] = []
    sub = 0

    def _next_id() -> int:
        nonlocal sub
        sub += 1
        return _sub_id(sp_id, sub)

    if orientation == "v":
        plot_top = y + value_band
        plot_bottom = y + h - label_band
        plot_h = max(plot_bottom - plot_top, 1)
        # Baseline (axis line)
        parts.append(
            rect_shape(
                _next_id(), f"{name}_axis", x, plot_bottom, w, max(_i(0.012 * EMU_PER_INCH), 1),
                axis_color,
            )
        )
        gap_total = w // (n * 4)  # ~25% of one slot
        bar_w = max((w - gap_total) // n, 1)
        gap = (w - bar_w * n) // max(n + 1, 1)
        for i, (lbl, val, col) in enumerate(items):
            v = max(0.0, float(val))
            bh = _i(plot_h * (v / vmax))
            bx = x + gap + i * (bar_w + gap)
            by_top = plot_bottom - bh
            parts.append(
                rect_shape(
                    _next_id(), f"{name}_bar{i}", bx, by_top, bar_w, max(bh, 1),
                    col or bar_color,
                )
            )
            # Value label above
            if show_values:
                parts.append(
                    text_box(
                        _next_id(), f"{name}_val{i}", bx, by_top - value_band,
                        bar_w, value_band, value_format.format(v),
                        size_pt=font_size_pt, color=value_color, font=font, align="ctr",
                    )
                )
            # Category label below
            parts.append(
                text_box(
                    _next_id(), f"{name}_lbl{i}", bx, plot_bottom, bar_w, label_band,
                    lbl, size_pt=font_size_pt, color=label_color, font=font, align="ctr",
                )
            )
    else:  # horizontal
        # Reserve a left band for category labels.
        label_band_w = max(_i(w * 0.22), label_band)
        plot_left = x + label_band_w
        plot_right = x + w - (value_band if show_values else 0)
        plot_w = max(plot_right - plot_left, 1)
        # Baseline (vertical axis on the left)
        axis_w = max(_i(0.012 * EMU_PER_INCH), 1)
        parts.append(
            rect_shape(
                _next_id(), f"{name}_axis", plot_left - axis_w, y, axis_w, h, axis_color,
            )
        )
        slot_h = h // n
        bar_h = max(_i(slot_h * 0.6), 1)
        for i, (lbl, val, col) in enumerate(items):
            v = max(0.0, float(val))
            bw = _i(plot_w * (v / vmax))
            slot_y = y + i * slot_h + (slot_h - bar_h) // 2
            parts.append(
                rect_shape(
                    _next_id(), f"{name}_bar{i}", plot_left, slot_y, max(bw, 1), bar_h,
                    col or bar_color,
                )
            )
            # Category label on the left
            parts.append(
                text_box(
                    _next_id(), f"{name}_lbl{i}", x, slot_y, label_band_w - axis_w, bar_h,
                    lbl, size_pt=font_size_pt, color=label_color, font=font, align="r",
                )
            )
            if show_values:
                parts.append(
                    text_box(
                        _next_id(), f"{name}_val{i}", plot_left + bw, slot_y,
                        value_band, bar_h, value_format.format(v),
                        size_pt=font_size_pt, color=value_color, font=font, align="l",
                    )
                )
    return "".join(parts)


def line_chart_shape(
    sp_id: int,
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    series: list[tuple[str, list[float], str | None]],
    x_labels: list[str] | None = None,
    show_markers: bool = True,
    axis_color: str = DEFAULT_PALETTE.border,
    label_color: str = DEFAULT_PALETTE.dark,
    line_width_emu: int = 19050,
    marker_radius_emu: int = 38100,
    font_size_pt: int = 9,
    font: str = DEFAULT_FONT,
) -> str:
    """Composite line chart.

    `series` is `[(name, values, color_or_None), ...]`. All series
    share the same x-axis (their length is taken from the longest
    series; shorter ones are padded with the last value).
    `x_labels` aligns to the x-axis category positions; if None, no
    bottom labels are drawn.
    """
    if not series:
        return ""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    n_pts = max(len(vals) for _, vals, _ in series)
    if n_pts < 2:
        # Need at least two points to draw a line.
        return ""
    all_vals = [v for _, vals, _ in series for v in vals]
    vmin = min(all_vals)
    vmax = max(all_vals)
    if vmax == vmin:
        vmax = vmin + 1.0
    label_band = _i(font_size_pt * 100 * 2.2) if x_labels else 0
    plot_top = y
    plot_bottom = y + h - label_band
    plot_h = max(plot_bottom - plot_top, 1)

    parts: list[str] = []
    sub = 0

    def _next_id() -> int:
        nonlocal sub
        sub += 1
        return _sub_id(sp_id, sub)

    # X axis line at the bottom of the plot area.
    axis_h = max(_i(0.012 * EMU_PER_INCH), 1)
    parts.append(
        rect_shape(
            _next_id(), f"{name}_axis", x, plot_bottom, w, axis_h, axis_color,
        )
    )

    step = w // max(n_pts - 1, 1)

    def _y_for(v: float) -> int:
        return plot_bottom - _i(plot_h * ((v - vmin) / (vmax - vmin)))

    for s_idx, (_s_name, vals, col) in enumerate(series):
        color = col or DEFAULT_PALETTE.purple
        # Pad short series with their last value so the line still
        # spans the full x range. (Caller can opt out by giving every
        # series the same length.)
        padded = list(vals) + [vals[-1]] * (n_pts - len(vals)) if vals else [0.0] * n_pts
        pts: list[tuple[int, int]] = []
        for i, v in enumerate(padded):
            px = x + i * step
            py = _y_for(float(v))
            pts.append((px, py))
        for i in range(len(pts) - 1):
            x1, y1 = pts[i]
            x2, y2 = pts[i + 1]
            parts.append(
                _segment_line(
                    _next_id(), f"{name}_s{s_idx}_seg{i}", x1, y1, x2, y2, color,
                    width_emu=line_width_emu,
                )
            )
        if show_markers:
            for i, (px, py) in enumerate(pts):
                parts.append(
                    _ellipse_marker(
                        _next_id(), f"{name}_s{s_idx}_m{i}", px, py, marker_radius_emu, color,
                    )
                )

    if x_labels:
        for i in range(n_pts):
            lbl = x_labels[i] if i < len(x_labels) else ""
            cx = x + i * step
            parts.append(
                text_box(
                    _next_id(), f"{name}_xl{i}", cx - step // 2, plot_bottom,
                    step, label_band, lbl,
                    size_pt=font_size_pt, color=label_color, font=font, align="ctr",
                )
            )
    return "".join(parts)


def pie_chart_shape(
    sp_id: int,
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    slices: list[tuple[str, float, str | None]],
    palette: Palette = DEFAULT_PALETTE,
) -> str:
    """Pie chart using <a:prstGeom prst="pie"> sectors.

    Each slice is a separate <p:sp> covering the same bounding box,
    with adj1/adj2 set to the start/end angles (units = 60000ths of
    a degree, 0 = 3 o'clock, sweeping clockwise).

    Slices with non-positive values are skipped. Labels are NOT
    rendered inline (the LLM can compose pill labels around the
    pie if it needs them); keeping this primitive label-free avoids
    overlap heuristics inside the deterministic emitter.
    """
    if not slices:
        return ""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    # Square the bounding box to keep the pie circular (use min side,
    # center inside the requested rect).
    side = min(w, h)
    cx = x + (w - side) // 2
    cy = y + (h - side) // 2

    total = sum(max(0.0, float(v)) for _, v, _ in slices)
    if total <= 0:
        return ""

    auto_colors = [
        palette.purple, palette.purple_lt, palette.amber, palette.green,
        palette.muted, palette.purple_dk, palette.purple_bg, palette.dark,
    ]

    parts: list[str] = []
    cursor = 0  # 60000ths of a degree
    full = 360 * 60000
    sub = 0
    for i, (_, val, col) in enumerate(slices):
        v = max(0.0, float(val))
        if v <= 0:
            continue
        sweep = round(full * (v / total))
        start = cursor
        end = (cursor + sweep) % full
        cursor = (cursor + sweep) % full
        sub += 1
        sid = _sub_id(sp_id, sub)
        fill = col or auto_colors[i % len(auto_colors)]
        parts.append(
            f'<p:sp><p:nvSpPr>'
            f'<p:cNvPr id="{sid}" name="{_xml_escape(name)}_s{i}"/>'
            f"<p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
            f'<p:spPr>'
            f'<a:xfrm><a:off x="{cx}" y="{cy}"/><a:ext cx="{side}" cy="{side}"/></a:xfrm>'
            f'<a:prstGeom prst="pie">'
            f'<a:avLst>'
            f'<a:gd name="adj1" fmla="val {start}"/>'
            f'<a:gd name="adj2" fmla="val {end}"/>'
            f"</a:avLst>"
            f"</a:prstGeom>"
            f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
            f"</p:spPr>"
            f"<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>"
            f"</p:sp>"
        )
    return "".join(parts)


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
