"""
Assemble a slide XML from a Blueprint slide + figure renderer output.

Replaces the body-area placeholder in a content layout slide with
shape XML produced by the figure renderer, and updates title text.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

from .figure_renderers import renderer_for
from .figure_renderers.base import EMUBox, RenderContext
from .shapes import DEFAULT_FONT, DEFAULT_PALETTE, Palette, inch, palette_from_theme
from .theme_loader import ThemeParseError, load_theme

DEFAULT_BODY_AREA = EMUBox(x=inch(0.5), y=inch(1.6), w=inch(12.3), h=inch(5.4))

_logger = logging.getLogger(__name__)


def _slot_render_enabled() -> bool:
    return os.environ.get("FF_SLOT_RENDER", "0") == "1"


def _theme_inheritance_enabled() -> bool:
    return os.environ.get("FF_THEME_INHERITANCE", "0") == "1"


def _resolve_palette(palette: Palette, theme_pptx_bytes: bytes | None) -> Palette:
    if not _theme_inheritance_enabled() or theme_pptx_bytes is None:
        return palette
    try:
        theme = load_theme(theme_pptx_bytes)
        return palette_from_theme(theme)
    except (ThemeParseError, Exception) as e:
        _logger.warning(
            "FF_THEME_INHERITANCE enabled but theme load failed (%s); "
            "falling back to provided palette",
            e,
        )
        return palette


def _pick_figure_slot(slots: list[dict]) -> dict | None:
    figure_slots = [s for s in slots if s.get("kind") == "figure"]
    if not figure_slots:
        return None
    return max(
        figure_slots,
        key=lambda s: int(s.get("w", 0)) * int(s.get("h", 0)),
    )


def _slot_to_box(slot: dict) -> EMUBox:
    return EMUBox(
        x=int(slot["x"]),
        y=int(slot["y"]),
        w=int(slot["w"]),
        h=int(slot["h"]),
    )


@dataclass
class RenderRequest:
    slide_index: int
    layout: str
    figure_type: str | None
    content: dict
    body_area: EMUBox = DEFAULT_BODY_AREA


def render_content_slide(
    slide_xml: str,
    req: RenderRequest,
    palette: Palette = DEFAULT_PALETTE,
    font: str = DEFAULT_FONT,
    start_shape_id: int = 1000,
    slots: list[dict] | None = None,
    theme_pptx_bytes: bytes | None = None,
) -> str:
    """Return updated slide XML with:
      1. Title placeholder text replaced.
      2. Body / content / subtitle placeholders stripped (we inject our
         own shapes in their place; leaving them in shows the template's
         placeholder text like "B" or "本文をここに入れる" bleeding
         through behind our figure).
      3. Figure shapes injected before </p:spTree>.

    Decorative (non-placeholder) shapes like the CONTENT ribbon or the
    company logo in the corner are preserved — they're not inside
    <p:ph> so the stripper leaves them alone.
    """
    out = slide_xml

    title = req.content.get("title")
    if title:
        out = _replace_title(out, title)

    if req.figure_type:
        out = _strip_body_placeholders(out)
        renderer = renderer_for(req.figure_type)
        vr = renderer.validate(req.content)
        if not vr.ok:
            raise ValueError(f"invalid content for {req.figure_type}: {vr.errors}")
        effective_palette = _resolve_palette(palette, theme_pptx_bytes)
        ctx = RenderContext(palette=effective_palette, font=font, next_shape_id=start_shape_id)
        container = req.body_area
        if _slot_render_enabled() and slots:
            figure_slot = _pick_figure_slot(slots)
            if figure_slot is not None:
                container = _slot_to_box(figure_slot)
            else:
                _logger.warning(
                    "FF_SLOT_RENDER enabled but no figure-kind slot found; "
                    "falling back to DEFAULT_BODY_AREA",
                )
        result = renderer.render(req.content, container, ctx)
        out = _inject_shapes(out, result.shapes_xml)

    return out


# <p:ph> placeholder types — see ECMA-376 §19.7.10. Anything not in
# this set gets stripped so our figure shapes don't sit on top of the
# template's "本文をここに入れる" filler.
_TITLE_PH_TYPES = {"title", "ctrTitle"}


def _replace_title(slide_xml: str, title: str) -> str:
    """Replace the first <a:t>...</a:t> inside a title placeholder.

    Matches any <p:sp> whose <p:ph> has type="title" / "ctrTitle" or
    (when type is omitted) idx="0" — the three ways PowerPoint marks a
    title box in practice.
    """
    pattern = re.compile(
        r'(<p:sp\b[^>]*>.*?<p:ph\b[^/>]*'
        r'(?:type="(?:title|ctrTitle)"|idx="0")'
        r'[^/>]*/?>.*?)<a:t>[^<]*</a:t>',
        re.DOTALL,
    )
    replacement = r"\1<a:t>" + _escape(title) + r"</a:t>"
    new, n = pattern.subn(replacement, slide_xml, count=1)
    if n == 0:
        # Fallback: replace the very first <a:t> text run in the slide.
        new = re.sub(r"<a:t>[^<]*</a:t>", f"<a:t>{_escape(title)}</a:t>", slide_xml, count=1)
    return new


def _strip_body_placeholders(slide_xml: str) -> str:
    """Remove any <p:sp> that represents a non-title placeholder.

    Placeholder shapes are the ones whose <p:nvSpPr> contains <p:ph>.
    Template decorations (logos, ribbon banners, footer lines) are
    non-placeholder <p:sp> or <p:pic> / <p:grpSp> — those pass through
    untouched.
    """
    sp_block = re.compile(r"<p:sp\b[^>]*>.*?</p:sp>", re.DOTALL)

    def _keep(match: re.Match) -> str:
        block = match.group(0)
        ph_match = re.search(r"<p:ph\b([^/>]*)/?>", block)
        if not ph_match:
            return block  # decoration; keep
        attrs = ph_match.group(1)
        type_match = re.search(r'type="([^"]+)"', attrs)
        if type_match and type_match.group(1) in _TITLE_PH_TYPES:
            return block  # title — keep (text was replaced above)
        # No type + idx="0" also means title
        if not type_match and re.search(r'idx="0"', attrs):
            return block
        return ""  # body / content / subtitle / etc — drop

    return sp_block.sub(_keep, slide_xml)


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _inject_shapes(slide_xml: str, shapes: list[str]) -> str:
    """Insert shape XML fragments before </p:spTree>."""
    blob = "\n".join(shapes)
    return slide_xml.replace("</p:spTree>", f"{blob}\n</p:spTree>", 1)
