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
from .shapes import (
    DEFAULT_FONT,
    DEFAULT_PALETTE,
    Palette,
    _xml_escape,
    inch,
    palette_from_theme,
)
from .theme_loader import ThemeParseError, load_theme

DEFAULT_BODY_AREA = EMUBox(x=inch(0.5), y=inch(1.6), w=inch(12.3), h=inch(5.4))
_BODY_AREA_4_3 = EMUBox(x=inch(0.4), y=inch(1.3), w=inch(9.2), h=inch(5.9))
_SLIDE_CX_16_9 = 12192000
_SLIDE_CY_16_9 = 6858000
_SLIDE_CX_4_3 = 9144000

_logger = logging.getLogger(__name__)


def default_body_area_for(slide_size: tuple[int, int] | None) -> EMUBox:
    """Return a reasonable body area for the given slide size.

    16:9 uses the legacy DEFAULT_BODY_AREA. 4:3 uses proportionally
    adjusted margins that fit the narrower canvas. Other ratios scale
    from the 16:9 baseline relative to the slide cx/cy.
    """
    if slide_size is None:
        return DEFAULT_BODY_AREA
    cx, cy = slide_size
    if cx <= 0 or cy <= 0:
        return DEFAULT_BODY_AREA
    if abs(cx - _SLIDE_CX_16_9) <= 1000 and abs(cy - _SLIDE_CY_16_9) <= 1000:
        return DEFAULT_BODY_AREA
    if abs(cx - _SLIDE_CX_4_3) <= 1000:
        return _BODY_AREA_4_3
    sx = cx / _SLIDE_CX_16_9
    sy = cy / _SLIDE_CY_16_9
    return EMUBox(
        x=int(DEFAULT_BODY_AREA.x * sx),
        y=int(DEFAULT_BODY_AREA.y * sy),
        w=int(DEFAULT_BODY_AREA.w * sx),
        h=int(DEFAULT_BODY_AREA.h * sy),
    )


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


def _legacy_text_for_slot(slot_id: str, content: dict) -> str | None:
    legacy: dict[str, str | None] = {
        "title": content.get("title"),
        "body_main": content.get("body") or content.get("body_main"),
        "footer": content.get("footer") or content.get("note"),
        "subtitle": content.get("subtitle"),
        "footnote": content.get("footer") or content.get("note"),
    }
    v = legacy.get(slot_id)
    if isinstance(v, str) and v:
        return v
    return None


def _resolve_slot_text(slot: dict, req: RenderRequest) -> str | None:
    slot_id = str(slot.get("id", ""))
    entry = req.content.get("slots", {}).get(slot_id) if isinstance(
        req.content.get("slots"), dict
    ) else None
    if isinstance(entry, dict) and isinstance(entry.get("text"), str):
        return entry["text"] or None
    if isinstance(entry, str):
        return entry or None
    if entry is None:
        return _legacy_text_for_slot(slot_id, req.content)
    return None


def _resolve_slot_list(slot: dict, req: RenderRequest) -> list[str] | str | None:
    slot_id = str(slot.get("id", ""))
    entry = req.content.get("slots", {}).get(slot_id) if isinstance(
        req.content.get("slots"), dict
    ) else None
    if isinstance(entry, dict):
        items = entry.get("items")
        if isinstance(items, list):
            return [str(i) for i in items if isinstance(i, (str, int, float))]
        if isinstance(entry.get("text"), str):
            return entry["text"] or None
    if isinstance(entry, list):
        return [str(i) for i in entry if isinstance(i, (str, int, float))]
    if isinstance(entry, str):
        return entry or None
    if entry is None:
        return _legacy_text_for_slot(slot_id, req.content)
    return None


def _resolve_image_content(slot: dict, req: RenderRequest) -> dict | None:
    slot_id = str(slot.get("id", ""))
    slots_map = req.content.get("slots")
    if not isinstance(slots_map, dict):
        return None
    entry = slots_map.get(slot_id)
    if not isinstance(entry, dict):
        return None
    if isinstance(entry.get("image_slot"), dict):
        return entry["image_slot"]
    if entry.get("asset_id"):
        return entry
    return None


def _render_text_slot(
    text: str, slot_rect: dict, ctx: RenderContext
) -> tuple[str, int]:
    x = int(slot_rect["x"])
    y = int(slot_rect["y"])
    w = int(slot_rect["w"])
    h = int(slot_rect["h"])
    sp_id = ctx.next_shape_id
    color = ctx.palette.black
    font = ctx.font
    xml = (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sp_id}" name="slot-text-{sp_id}"/>'
        f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        f"<p:spPr>"
        f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f"<a:noFill/>"
        f"</p:spPr>"
        f'<p:txBody><a:bodyPr wrap="square" anchor="t"/><a:lstStyle/>'
        f'<a:p><a:pPr algn="l"/>'
        f'<a:r><a:rPr lang="ja-JP" sz="1100" b="0">'
        f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        f'<a:latin typeface="{font}"/>'
        f'<a:ea typeface="{font}"/>'
        f"</a:rPr>"
        f"<a:t>{_xml_escape(text)}</a:t></a:r>"
        f"</a:p></p:txBody>"
        f"</p:sp>"
    )
    return xml, sp_id + 1


def _render_slots(
    slots: list[dict],
    req: RenderRequest,
    ctx: RenderContext,
) -> tuple[list[str], int]:
    fragments: list[str] = []
    next_id = ctx.next_shape_id
    processed_kinds: set[str] = set()

    figure_slots = [s for s in slots if s.get("kind") == "figure"]
    figure_slot_to_use: dict | None = None
    if req.figure_type and figure_slots:
        body_main = [s for s in figure_slots if s.get("id") == "body_main"]
        if body_main:
            figure_slot_to_use = body_main[0]
        elif len(figure_slots) == 1:
            figure_slot_to_use = figure_slots[0]
        else:
            figure_slot_to_use = max(
                figure_slots,
                key=lambda s: int(s.get("w", 0)) * int(s.get("h", 0)),
            )

    for slot in slots:
        kind = slot.get("kind")
        if kind == "text":
            text = _resolve_slot_text(slot, req)
            if not text:
                continue
            if slot.get("id") == "title":
                continue
            xml, next_id = _render_text_slot(
                text,
                slot,
                RenderContext(
                    palette=ctx.palette,
                    font=ctx.font,
                    next_shape_id=next_id,
                    media=ctx.media,
                    slide_index=ctx.slide_index,
                ),
            )
            fragments.append(xml)
        elif kind == "list":
            value = _resolve_slot_list(slot, req)
            if not value:
                continue
            if isinstance(value, list):
                text = "\n".join(f"• {line}" for line in value if line)
            else:
                text = value
            if not text:
                continue
            xml, next_id = _render_text_slot(
                text,
                slot,
                RenderContext(
                    palette=ctx.palette,
                    font=ctx.font,
                    next_shape_id=next_id,
                    media=ctx.media,
                    slide_index=ctx.slide_index,
                ),
            )
            fragments.append(xml)
        elif kind == "figure":
            if "figure" in processed_kinds:
                continue
            if not req.figure_type:
                continue
            if figure_slot_to_use is None or slot is not figure_slot_to_use:
                continue
            renderer = renderer_for(req.figure_type)
            vr = renderer.validate(req.content)
            if not vr.ok:
                raise ValueError(
                    f"invalid content for {req.figure_type}: {vr.errors}"
                )
            container = _slot_to_box(slot)
            result = renderer.render(
                req.content,
                container,
                RenderContext(
                    palette=ctx.palette,
                    font=ctx.font,
                    next_shape_id=next_id,
                    media=ctx.media,
                    slide_index=ctx.slide_index,
                ),
            )
            fragments.extend(result.shapes_xml)
            next_id = result.next_shape_id
            processed_kinds.add("figure")
        elif kind == "image":
            image_content = _resolve_image_content(slot, req)
            if image_content is None:
                continue
            renderer = renderer_for("image_slot")
            vr = renderer.validate(image_content)
            if not vr.ok:
                _logger.debug(
                    "image_slot validation failed for slot %s: %s",
                    slot.get("id"),
                    vr.errors,
                )
                continue
            container = _slot_to_box(slot)
            result = renderer.render(
                image_content,
                container,
                RenderContext(
                    palette=ctx.palette,
                    font=ctx.font,
                    next_shape_id=next_id,
                    media=ctx.media,
                    slide_index=ctx.slide_index,
                ),
            )
            fragments.extend(result.shapes_xml)
            next_id = result.next_shape_id
        elif kind in ("table", "fixed"):
            _logger.debug("skipping slot kind=%s id=%s", kind, slot.get("id"))
            continue
        else:
            _logger.debug(
                "unknown slot kind=%s id=%s; skipping", kind, slot.get("id")
            )
            continue

    if req.figure_type and "figure" not in processed_kinds:
        renderer = renderer_for(req.figure_type)
        vr = renderer.validate(req.content)
        if not vr.ok:
            raise ValueError(
                f"invalid content for {req.figure_type}: {vr.errors}"
            )
        if slots and not figure_slots:
            _logger.warning(
                "FF_SLOT_RENDER enabled but no figure-kind slot found; "
                "falling back to DEFAULT_BODY_AREA",
            )
        container = req.body_area
        result = renderer.render(
            req.content,
            container,
            RenderContext(
                palette=ctx.palette,
                font=ctx.font,
                next_shape_id=next_id,
                media=ctx.media,
                slide_index=ctx.slide_index,
            ),
        )
        fragments.extend(result.shapes_xml)
        next_id = result.next_shape_id

    return fragments, next_id


def render_content_slide(
    slide_xml: str,
    req: RenderRequest,
    palette: Palette = DEFAULT_PALETTE,
    font: str = DEFAULT_FONT,
    start_shape_id: int = 1000,
    slots: list[dict] | None = None,
    theme_pptx_bytes: bytes | None = None,
    slide_size: tuple[int, int] | None = None,
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

    if slide_size is not None and req.body_area == DEFAULT_BODY_AREA:
        req = RenderRequest(
            slide_index=req.slide_index,
            layout=req.layout,
            figure_type=req.figure_type,
            content=req.content,
            body_area=default_body_area_for(slide_size),
        )

    title = req.content.get("title")
    if title:
        out = _replace_title(out, title)

    # TOC slides: populate the template's "項目タイトル" slots with the
    # blueprint's item list before the generic prompt stripper runs
    # (the stripper would otherwise blank them out entirely).
    if req.layout == "toc":
        items = req.content.get("items")
        if isinstance(items, list):
            toc_items = [str(x) for x in items if isinstance(x, (str, int, float))]
            if toc_items:
                out = _replace_toc_items(out, toc_items)

    # Strip decoration text boxes containing template prompt filler
    # (e.g. "本文 / 図解 / 表をここに配置", "このセクションの概要を…").
    # These shapes have no <p:ph> so _strip_body_placeholders misses
    # them; without this they bleed through on every rendered slide.
    out = _strip_prompt_decoration(out)
    # Drop leftover title-prompt shapes after _replace_title has
    # filled one of them (multiple "セクションタイトル" shapes) or
    # when the blueprint had no title at all.
    out = _strip_unused_title_prompts(out)

    effective_palette = _resolve_palette(palette, theme_pptx_bytes)

    if _slot_render_enabled() and slots is not None:
        out = _strip_body_placeholders(out)
        ctx = RenderContext(
            palette=effective_palette, font=font, next_shape_id=start_shape_id
        )
        fragments, _next_id = _render_slots(slots, req, ctx)
        if fragments:
            out = _inject_shapes(out, fragments)
        return out

    if req.figure_type:
        out = _strip_body_placeholders(out)
        renderer = renderer_for(req.figure_type)
        vr = renderer.validate(req.content)
        if not vr.ok:
            raise ValueError(f"invalid content for {req.figure_type}: {vr.errors}")
        ctx = RenderContext(
            palette=effective_palette, font=font, next_shape_id=start_shape_id
        )
        container = req.body_area
        result = renderer.render(req.content, container, ctx)
        out = _inject_shapes(out, result.shapes_xml)

    return out


# <p:ph> placeholder types — see ECMA-376 §19.7.10. Anything not in
# this set gets stripped so our figure shapes don't sit on top of the
# template's "本文をここに入れる" filler.
_TITLE_PH_TYPES = {"title", "ctrTitle"}

# Japanese corporate templates commonly embed the placeholder prompt
# text directly into decoration text boxes (plain <p:sp> with no <p:ph>
# marker), rather than inheriting it from the slide layout. The body
# placeholder stripper can't reach these because it only touches shapes
# whose <p:nvSpPr> contains <p:ph>, so these strings survive the render
# and show up on every slide as "bleed-through" template filler.
#
# _TITLE_PROMPT_PATTERNS: text-box prompts that a blueprint title should
#   REPLACE (e.g. "コンテンツタイトル" → the actual slide title).
# _BODY_PROMPT_PATTERNS: text-box prompts that are pure filler and
#   should be stripped entirely once we've injected our own content.
_TITLE_PROMPT_PATTERNS: tuple[str, ...] = (
    "コンテンツタイトル",
    "セクションタイトル",
    "タイトルをここに入れる",
)
_BODY_PROMPT_PATTERNS: tuple[str, ...] = (
    "本文をここに入れる",
    "本文 / 図解 / 表をここに配置",
    "本文／図解／表をここに配置",
    "本文 / 図版 / 表をここに配置",
    "本文／図版／表をここに配置",
    "このセクションの概要を",
    "サブタイトル・コンセプト文",
    "項目タイトル",
    "Section title",
    "本セクションの読了目安",
)

_SP_BLOCK_RE = re.compile(r"<p:sp\b[^>]*>.*?</p:sp>", re.DOTALL)
_AT_RUN_RE = re.compile(r"<a:t>[^<]*</a:t>")


def _sp_text(block: str) -> str:
    return "".join(re.findall(r"<a:t>([^<]*)</a:t>", block))


def _replace_first_a_t(block: str, new_text: str) -> str:
    """Replace the first <a:t>...</a:t> run in `block` with new_text
    and blank every subsequent run in the same shape.

    Needed because template title shapes often span multiple runs for
    styling (e.g. "タイトルを" + "ここに入れる。" as separate runs with
    different fonts); if we only overwrite the first run, the tail
    stays visible.
    """
    count = 0

    def _rep(_m: re.Match) -> str:
        nonlocal count
        count += 1
        if count == 1:
            return f"<a:t>{_escape(new_text)}</a:t>"
        return "<a:t></a:t>"

    return _AT_RUN_RE.sub(_rep, block)


_TITLE_PH_RE = re.compile(
    r'<p:ph\b[^/>]*(?:type="(?:title|ctrTitle)"|idx="0")[^/>]*/?>',
)


def _replace_title(slide_xml: str, title: str) -> str:
    """Replace the title text on a slide.

    Pass 1: find the first <p:sp> that contains a proper title
    placeholder (<p:ph type="title"|"ctrTitle"|idx="0">). Overwrite
    its first <a:t> run with the new title and blank every subsequent
    run inside the same shape — corporate templates frequently split
    the title across multiple styled runs (e.g. "タイトルを" + "ここに
    入れる。"); overwriting only the first run leaves the tail visible.

    Pass 2 (fallback): templates that don't use proper placeholders
    embed the prompt as decoration text. Find the first <p:sp> whose
    visible text matches _TITLE_PROMPT_PATTERNS and rewrite it the
    same way.
    """
    replaced = False

    def _pass1(match: re.Match) -> str:
        nonlocal replaced
        block = match.group(0)
        if replaced:
            return block
        if _TITLE_PH_RE.search(block):
            replaced = True
            return _replace_first_a_t(block, title)
        return block

    out = _SP_BLOCK_RE.sub(_pass1, slide_xml)
    if replaced:
        return out

    def _pass2(match: re.Match) -> str:
        nonlocal replaced
        block = match.group(0)
        if replaced:
            return block
        text = _sp_text(block)
        if any(p in text for p in _TITLE_PROMPT_PATTERNS):
            replaced = True
            return _replace_first_a_t(block, title)
        return block

    return _SP_BLOCK_RE.sub(_pass2, out)


def _replace_toc_items(slide_xml: str, items: list[str]) -> str:
    """Populate the template's TOC item shapes with real section titles.

    Templates typically stamp out N "項目タイトル" prompt shapes for
    the TOC. We walk the slide in document order and replace those
    shapes' text with items[0], items[1], ... in turn. Extra prompt
    shapes (more template slots than items) are stripped; extra items
    (more items than slots) are dropped silently.
    """
    i = 0

    def _rep(match: re.Match) -> str:
        nonlocal i
        block = match.group(0)
        text = _sp_text(block)
        if "項目タイトル" not in text and "Section title" not in text:
            return block
        if i >= len(items):
            return ""  # extra template slot; drop
        new = _replace_first_a_t(block, items[i])
        i += 1
        return new

    return _SP_BLOCK_RE.sub(_rep, slide_xml)


def _strip_prompt_decoration(slide_xml: str) -> str:
    """Remove decoration <p:sp> shapes containing known body-prompt text.

    These shapes have no <p:ph> so _strip_body_placeholders leaves them
    alone. They're the "本文 / 図解 / 表をここに配置",
    "このセクションの概要を…" etc. filler that bleeds through on every
    slide in templates that don't use real placeholders.
    """
    def _keep(match: re.Match) -> str:
        block = match.group(0)
        text = _sp_text(block)
        if any(p in text for p in _BODY_PROMPT_PATTERNS):
            return ""
        return block

    return _SP_BLOCK_RE.sub(_keep, slide_xml)


def _strip_unused_title_prompts(slide_xml: str) -> str:
    """Remove decoration shapes still holding a title prompt after title
    replacement — happens when the blueprint didn't supply a title, or
    when the template has multiple "セクションタイトル" text boxes and
    only the first gets replaced.
    """
    def _keep(match: re.Match) -> str:
        block = match.group(0)
        text = _sp_text(block)
        if any(p in text for p in _TITLE_PROMPT_PATTERNS):
            return ""
        return block

    return _SP_BLOCK_RE.sub(_keep, slide_xml)


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
