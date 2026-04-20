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
    """Return updated slide XML with title replaced and figure shapes injected."""
    out = slide_xml

    title = req.content.get("title")
    if title:
        out = _replace_title(out, title)

    if req.figure_type:
        renderer = renderer_for(req.figure_type)
        vr = renderer.validate(req.content)
        if not vr.ok:
            raise ValueError(f"invalid content for {req.figure_type}: {vr.errors}")
        ctx = RenderContext(palette=palette, font=font, next_shape_id=start_shape_id)
        result = renderer.render(req.content, req.body_area, ctx)
        out = _inject_shapes(out, result.shapes_xml)

    return out


def _replace_title(slide_xml: str, title: str) -> str:
    """Replace the first <a:t>...</a:t> inside a title placeholder."""
    pattern = re.compile(
        r'(<p:sp>\s*<p:nvSpPr>.*?ph type="title".*?)<a:t>[^<]*</a:t>',
        re.DOTALL,
    )
    replacement = r"\1<a:t>" + _escape(title) + r"</a:t>"
    new, n = pattern.subn(replacement, slide_xml, count=1)
    if n == 0:
        # Fallback: replace very first <a:t>
        new = re.sub(r"<a:t>[^<]*</a:t>", f"<a:t>{_escape(title)}</a:t>", slide_xml, count=1)
    return new


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
