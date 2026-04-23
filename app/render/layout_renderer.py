"""
Assemble a slide XML from a Blueprint slide + figure renderer output.

Replaces the body-area placeholder in a content layout slide with
shape XML produced by the figure renderer, and updates title text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .figure_renderers import renderer_for
from .figure_renderers.base import EMUBox, RenderContext
from .shapes import DEFAULT_FONT, DEFAULT_PALETTE, Palette, inch

DEFAULT_BODY_AREA = EMUBox(x=inch(0.5), y=inch(1.6), w=inch(12.3), h=inch(5.4))


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
        ctx = RenderContext(palette=palette, font=font, next_shape_id=start_shape_id)
        result = renderer.render(req.content, req.body_area, ctx)
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
