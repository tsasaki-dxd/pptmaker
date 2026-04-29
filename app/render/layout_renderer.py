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
    fit_stack,
    inch,
    palette_from_theme,
)
from .theme_loader import ThemeParseError, load_theme

DEFAULT_BODY_AREA = EMUBox(x=inch(0.5), y=inch(1.6), w=inch(12.3), h=inch(5.4))
_BODY_AREA_4_3 = EMUBox(x=inch(0.4), y=inch(1.3), w=inch(9.2), h=inch(5.9))
# 16:9 widescreen at 10x5.625 inch — the layout PowerPoint calls
# "ワイドスクリーン (10 x 5.63 in)". cx coincides with classic 4:3
# (9144000 EMU) so checking width alone misclassifies it; the cy
# distinguishes them.
_BODY_AREA_WIDE_10IN = EMUBox(x=inch(0.4), y=inch(1.75), w=inch(9.2), h=inch(3.4))
_SLIDE_CX_16_9 = 12192000
_SLIDE_CY_16_9 = 6858000
_SLIDE_CX_4_3 = 9144000
_SLIDE_CY_4_3 = 6858000
_SLIDE_CX_WIDE_10IN = 9144000
_SLIDE_CY_WIDE_10IN = 5143500

_logger = logging.getLogger(__name__)


def default_body_area_for(slide_size: tuple[int, int] | None) -> EMUBox:
    """Return a reasonable body area for the given slide size.

    16:9 standard (13.333×7.5) uses DEFAULT_BODY_AREA.
    16:9 wide (10x5.625, "ワイドスクリーン") uses a smaller body box
    that actually fits — checking cx alone matches both widescreen
    and 4:3 (9144000 EMU each), so cy must also match.
    4:3 (10x7.5) uses the legacy _BODY_AREA_4_3.
    Other ratios scale from the 16:9 baseline relative to slide cx/cy.
    """
    if slide_size is None:
        return DEFAULT_BODY_AREA
    cx, cy = slide_size
    if cx <= 0 or cy <= 0:
        return DEFAULT_BODY_AREA
    if abs(cx - _SLIDE_CX_16_9) <= 1000 and abs(cy - _SLIDE_CY_16_9) <= 1000:
        return DEFAULT_BODY_AREA
    if abs(cx - _SLIDE_CX_WIDE_10IN) <= 1000 and abs(cy - _SLIDE_CY_WIDE_10IN) <= 1000:
        return _BODY_AREA_WIDE_10IN
    if abs(cx - _SLIDE_CX_4_3) <= 1000 and abs(cy - _SLIDE_CY_4_3) <= 1000:
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
    total_slides: int | None = None,
    extra_shapes_xml: list[str] | None = None,
    section_index: int | None = None,
    media: object | None = None,
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

    # Body-area resolution priority:
    #   1. explicit req.body_area (caller decided)
    #   2. detected from a body-prompt decoration shape on this slide
    #      (works for templates without <p:ph>, the common JP case)
    #   3. derived from slide dimensions (16:9, 10x5.625 wide, 4:3)
    #   4. fall back to DEFAULT_BODY_AREA
    # The detected rect wins over the slide-size guess because the
    # template author put the prompt shape exactly where the body
    # belongs; the slide-size fallback is at best a reasonable margin.
    if req.body_area == DEFAULT_BODY_AREA:
        body_rect = _detect_body_rect(out)
        if body_rect is not None:
            req = RenderRequest(
                slide_index=req.slide_index,
                layout=req.layout,
                figure_type=req.figure_type,
                content=req.content,
                body_area=EMUBox(
                    x=body_rect[0],
                    y=body_rect[1],
                    w=body_rect[2],
                    h=body_rect[3],
                ),
            )
        elif slide_size is not None:
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

    # Page footer: rewrite "NN / MM" → "current / total" so a 6-page
    # template fed into a 16-slide deck doesn't keep showing "/ 06".
    if total_slides is not None:
        out = _replace_page_counter(out, req.slide_index, total_slides)

    # Section divider: rewrite "SECTION NN" to match the actual
    # section this divider opens. Only applies when the caller knows
    # the slide's section index (handler.py counts section_divider
    # slides as it iterates).
    if section_index is not None and req.layout == "section_divider":
        out = _replace_section_number(out, section_index)

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

    # extra_shapes_xml takes precedence over the deterministic
    # figure-renderer / slot pipelines: when the layout designer LLM
    # produced a LayoutSpec for this slide, the caller emits the
    # spec and hands the resulting shape XML in here. Body placeholders
    # are still stripped so designer shapes don't sit on top of
    # template prompt text.
    if extra_shapes_xml:
        out = _strip_body_placeholders(out)
        out = _inject_shapes(out, extra_shapes_xml)
        return out

    if _slot_render_enabled() and slots is not None:
        out = _strip_body_placeholders(out)
        ctx = RenderContext(
            palette=effective_palette,
            font=font,
            next_shape_id=start_shape_id,
            media=media,  # type: ignore[arg-type]
            slide_index=req.slide_index,
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
            palette=effective_palette,
            font=font,
            next_shape_id=start_shape_id,
            media=media,  # type: ignore[arg-type]
            slide_index=req.slide_index,
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
    "本文／図解／図表をここに配置",
    "本文／図解／表をここに配置",
    "本文 / 図版 / 表をここに配置",
    "本文／図版／表をここに配置",
    # Full-width slash + half-width spaces — observed on the
    # DXDesignSystem template (template authors mix slash widths).
    "本文 ／ 図版 ／ 表をここに配置",
    "本文 ／ 図解 ／ 表をここに配置",
    "このセクションの概要を",
    "サブタイトル・コンセプト文",
    "項目タイトル",
    "Section title",
    "本セクションの読了目安",
)
# Templates sometimes ship a tiny "BODY" / "Body" label above the
# body area as a visual guide. Match exactly — "BODY" as a substring
# of legitimate content (e.g. an English title) shouldn't be stripped.
_BODY_PROMPT_EXACT_PATTERNS: tuple[str, ...] = (
    "BODY",
    "Body",
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


_A_RUN_RE = re.compile(r"<a:r\b.*?</a:r>", re.DOTALL)
_RPR_SZ_RE = re.compile(r'sz="(\d+)"')


def _replace_title_runs_in_block(block: str, new_text: str) -> str:
    """Replace the *title* run(s) in a shape with the given text,
    leaving smaller styled runs (labels, eyebrows) alone.

    Problem this solves: the DXDesignSystem content-slide title shape
    packs three runs into one <p:sp> — a pt8 "CONTENT" eyebrow, a pt9
    "CONTENT" label, and the pt22 "コンテンツタイトル" actual title.
    _replace_first_a_t would drop the blueprint title into the pt8
    eyebrow slot and blank out the pt22 slot entirely, leaving the
    slide with no visible title at all. This helper picks the run(s)
    with the largest `sz="..."` attribute — those are the title's own
    runs by construction — and rewrites only them. A multi-run title
    (cover "タイトルを" + "ここに入れる。") still collapses cleanly
    because both runs carry the same largest sz.

    Runs without an explicit sz attribute default to 0 in the
    comparison, which means a title whose sz is inherited from the
    list style would match as "smallest" and not get replaced —
    acceptable because in practice templates that set sz on the
    eyebrow always also set it on the title run.
    """
    runs = list(_A_RUN_RE.finditer(block))
    if not runs:
        # No runs at all: fall back to the first <a:t> replacement.
        return _replace_first_a_t(block, new_text)

    max_sz = 0
    for rm in runs:
        sz_m = _RPR_SZ_RE.search(rm.group(0))
        if sz_m:
            sz = int(sz_m.group(1))
            if sz > max_sz:
                max_sz = sz

    replaced = False

    def _rep(m: re.Match) -> str:
        nonlocal replaced
        run = m.group(0)
        sz_m = _RPR_SZ_RE.search(run)
        sz = int(sz_m.group(1)) if sz_m else 0
        if sz != max_sz:
            return run  # smaller styled run — leave it alone
        text_m = re.search(r"<a:t>[^<]*</a:t>", run)
        if not text_m:
            return run
        if not replaced:
            replaced = True
            return run.replace(text_m.group(0), f"<a:t>{_escape(new_text)}</a:t>")
        return run.replace(text_m.group(0), "<a:t></a:t>")

    out = _A_RUN_RE.sub(_rep, block)
    # If nothing matched (shape with no sz at all), fall back to the
    # first-a:t replacement so we still produce a title.
    return out if replaced else _replace_first_a_t(block, new_text)


_TITLE_PH_RE = re.compile(
    r'<p:ph\b[^/>]*(?:type="(?:title|ctrTitle)"|idx="0")[^/>]*/?>',
)
_BODY_PR_SELFCLOSING_RE = re.compile(r'<a:bodyPr\b([^/>]*)/>')
_BODY_PR_OPEN_RE = re.compile(r'<a:bodyPr\b([^>]*)>')


def _ensure_autofit_on_block(block: str) -> str:
    """Insert ``<a:normAutofit/>`` inside the shape's <a:bodyPr> so
    PowerPoint auto-shrinks text that overflows the box.

    Titles in the DXDesignSystem template ship with pt62 hardcoded —
    fine for the prompt "タイトルを / ここに入れる。" but way too big
    for a 13-char real title like "DXコンサルティング提案書", which
    then either wraps past the frame or spills off-slide. normAutofit
    lets PowerPoint pick a scaled-down font at render time while
    keeping our replace logic purely textual.
    """
    if "normAutofit" in block:
        return block  # already has it

    def _self_close(m: re.Match) -> str:
        attrs = m.group(1)
        return f"<a:bodyPr{attrs}><a:normAutofit/></a:bodyPr>"

    new, n = _BODY_PR_SELFCLOSING_RE.subn(_self_close, block, count=1)
    if n > 0:
        return new

    def _open(m: re.Match) -> str:
        attrs = m.group(1)
        return f"<a:bodyPr{attrs}><a:normAutofit/>"

    new, n = _BODY_PR_OPEN_RE.subn(_open, block, count=1)
    return new if n > 0 else block


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

    Either pass also attaches `<a:normAutofit/>` to the replaced
    shape's bodyPr so a title longer than the template's hardcoded
    font size shrinks to fit instead of spilling off the slide.
    """
    replaced = False

    def _pass1(match: re.Match) -> str:
        nonlocal replaced
        block = match.group(0)
        if replaced:
            return block
        if _TITLE_PH_RE.search(block):
            replaced = True
            return _ensure_autofit_on_block(_replace_title_runs_in_block(block, title))
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
            return _ensure_autofit_on_block(_replace_title_runs_in_block(block, title))
        return block

    return _SP_BLOCK_RE.sub(_pass2, out)


_XFRM_RE = re.compile(
    r'(<a:xfrm[^>]*>\s*<a:off\s+x=")(\d+)("\s+y=")(\d+)("\s*/>\s*<a:ext\s+cx=")'
    r'(\d+)("\s+cy=")(\d+)("\s*/>\s*</a:xfrm>)'
)


def _read_xfrm(block: str) -> tuple[int, int, int, int] | None:
    """Extract (x, y, cx, cy) from the first <a:xfrm> in a shape block."""
    m = _XFRM_RE.search(block)
    if not m:
        return None
    return (int(m.group(2)), int(m.group(4)), int(m.group(6)), int(m.group(8)))


def _write_xfrm(block: str, x: int, y: int, cx: int, cy: int) -> str:
    """Replace the <a:xfrm> off/ext values in a shape block."""
    return _XFRM_RE.sub(
        lambda m: (
            f'{m.group(1)}{x}{m.group(3)}{y}{m.group(5)}'
            f'{cx}{m.group(7)}{cy}{m.group(9)}'
        ),
        block,
        count=1,
    )


_NUMBER_PREFIX_RE = re.compile(r"^\s*(\d{1,2})\s*$")


def _replace_toc_items(slide_xml: str, items: list[str]) -> str:
    """Populate the template's TOC entries with real section titles.

    A TOC entry on the canonical corporate template is a *group* of
    shapes — a number prefix ("01"), a Japanese title ("項目タイトル"),
    sometimes a Section-title English subtitle, sometimes a horizontal
    rule. We anchor on the Japanese-title shape (every entry has one),
    then locate the number prefix by Y proximity. When the blueprint
    has more items than the template has entries, both shapes are
    cloned and the number is auto-incremented (06, 07, …); when fewer,
    trailing entries (anchor + number companion) are dropped.

    fit_stack drives the pitch computation so the whole list still fits
    inside the template's reserved Y range no matter how many items
    blueprint ships. English-subtitle "Section title" shapes are not
    cloned and get stripped by _strip_prompt_decoration downstream.

    Falls back to text-only rewrite when no anchor has a measurable
    <a:xfrm>, so templates we can't measure still get something useful.
    """
    if not items:
        return slide_xml

    matches = list(_SP_BLOCK_RE.finditer(slide_xml))

    # Step 1: locate anchors ("項目タイトル" shapes) with their rects.
    anchor_indices: list[int] = []
    anchor_rects: list[tuple[int, int, int, int] | None] = []
    for i, m in enumerate(matches):
        block = m.group(0)
        if "項目タイトル" not in _sp_text(block):
            continue
        anchor_indices.append(i)
        anchor_rects.append(_read_xfrm(block))

    if not anchor_indices:
        return slide_xml

    measurable_pairs = [
        (idx, rect)
        for idx, rect in zip(anchor_indices, anchor_rects, strict=True)
        if rect is not None
    ]
    if not measurable_pairs:
        return _replace_toc_items_textonly(slide_xml, items)

    # Step 2: container range + natural pitch from the measurable
    # anchors. Container height = first anchor top → last anchor bottom.
    first_anchor_idx, (first_x, first_y, first_w, first_h) = measurable_pairs[0]
    _, (_, last_y, _, last_h) = measurable_pairs[-1]
    container_h = max(first_h, (last_y + last_h) - first_y)
    natural_gap = 0
    if len(measurable_pairs) >= 2:
        natural_gap = max(
            0,
            measurable_pairs[1][1][1] - measurable_pairs[0][1][1] - measurable_pairs[0][1][3],
        )

    item_h, gap = fit_stack(
        container_h=container_h,
        n=len(items),
        natural_h=first_h,
        min_h=max(int(first_h * 0.45), 200_000),
        gap=natural_gap,
        min_gap=0,
    )
    pitch = item_h + gap

    # Step 3: pair each anchor with its number-prefix companion shape.
    # Companion = an <p:sp> whose text is just digits ("01", "02", …)
    # and whose Y center is closest to the anchor's Y center within
    # the natural pitch. Keep at most one companion per anchor.
    half_window = max(pitch, first_h) // 2 + 1
    number_companions: list[tuple[int, tuple[int, int, int, int]] | None] = []
    used_companion_indices: set[int] = set()
    for _a_idx, a_rect in zip(anchor_indices, anchor_rects, strict=True):
        if a_rect is None:
            number_companions.append(None)
            continue
        a_center = a_rect[1] + a_rect[3] // 2
        best: tuple[int, tuple[int, int, int, int]] | None = None
        best_dist = half_window
        for j, m in enumerate(matches):
            if j in anchor_indices or j in used_companion_indices:
                continue
            block = m.group(0)
            text = _sp_text(block).strip()
            if not _NUMBER_PREFIX_RE.match(text):
                continue
            r = _read_xfrm(block)
            if r is None:
                continue
            n_center = r[1] + r[3] // 2
            dist = abs(n_center - a_center)
            if dist < best_dist:
                best = (j, r)
                best_dist = dist
        if best is not None:
            used_companion_indices.add(best[0])
        number_companions.append(best)

    # Horizontal rule companions: each TOC entry often has a thin
    # rect (cx wide, cy 0 with a stroke) sitting just below it as a
    # separator. Pair each entry with the nearest rule by Y proximity
    # so cloning extras also clones their rules.
    rule_companions: list[tuple[int, tuple[int, int, int, int]] | None] = []
    used_rule_indices: set[int] = set()
    for _a_idx, a_rect in zip(anchor_indices, anchor_rects, strict=True):
        if a_rect is None:
            rule_companions.append(None)
            continue
        a_bottom = a_rect[1] + a_rect[3]
        best: tuple[int, tuple[int, int, int, int]] | None = None
        best_dist = half_window
        for j, m in enumerate(matches):
            if (
                j in anchor_indices
                or j in used_companion_indices
                or j in used_rule_indices
            ):
                continue
            block = m.group(0)
            text = _sp_text(block).strip()
            if text:
                continue  # rules carry no text
            r = _read_xfrm(block)
            if r is None:
                continue
            if r[3] > 20000:  # cy: rules are thin (often 0)
                continue
            if r[2] < 1_000_000:  # cx: rules span the TOC items column
                continue
            rule_top = r[1]
            dist = abs(rule_top - a_bottom)
            if dist < best_dist:
                best = (j, r)
                best_dist = dist
        if best is not None:
            used_rule_indices.add(best[0])
        rule_companions.append(best)

    # Reference offsets for cloning the extras: take the first anchor
    # whose companion we found; clone its number's and rule's
    # relative dx/dy/w/h.
    template_anchor_block = matches[first_anchor_idx].group(0)
    template_number_block: str | None = None
    template_number_offset: tuple[int, int, int, int] | None = None  # dx, dy, w, h
    for a_rect, comp in zip(anchor_rects, number_companions, strict=True):
        if a_rect is None or comp is None:
            continue
        n_idx, n_rect = comp
        template_number_block = matches[n_idx].group(0)
        template_number_offset = (
            n_rect[0] - a_rect[0],
            n_rect[1] - a_rect[1],
            n_rect[2],
            n_rect[3],
        )
        break

    template_rule_block: str | None = None
    template_rule_offset: tuple[int, int, int, int] | None = None
    for a_rect, comp in zip(anchor_rects, rule_companions, strict=True):
        if a_rect is None or comp is None:
            continue
        r_idx, r_rect = comp
        template_rule_block = matches[r_idx].group(0)
        template_rule_offset = (
            r_rect[0] - a_rect[0],
            r_rect[1] - a_rect[1],
            r_rect[2],
            r_rect[3],
        )
        break

    # Step 4: build the per-shape replacements.
    new_blocks: dict[int, str] = {}
    appended_clones: list[str] = []
    drop_indices: set[int] = set()

    for i, text in enumerate(items):
        new_anchor_y = first_y + pitch * i
        if i < len(anchor_indices):
            a_idx = anchor_indices[i]
            orig = matches[a_idx].group(0)
            base = orig if _XFRM_RE.search(orig) else template_anchor_block
            new_anchor = _replace_first_a_t(base, text)
            new_anchor = _write_xfrm(new_anchor, first_x, new_anchor_y, first_w, item_h)
            new_anchor = _ensure_autofit_on_block(new_anchor)
            new_blocks[a_idx] = new_anchor

            comp = number_companions[i]
            if comp is not None:
                n_idx, n_rect = comp
                # Preserve the companion's offset from its own anchor;
                # the absolute Y must shift by the same delta the anchor moved.
                anchor_rect = anchor_rects[i]
                if anchor_rect is not None:
                    dy = n_rect[1] - anchor_rect[1]
                    dx = n_rect[0] - anchor_rect[0]
                else:
                    dy = template_number_offset[1] if template_number_offset else 0
                    dx = template_number_offset[0] if template_number_offset else 0
                new_n_y = new_anchor_y + dy
                new_n_x = first_x + dx
                new_n = _replace_first_a_t(matches[n_idx].group(0), f"{i + 1:02d}")
                new_n = _write_xfrm(new_n, new_n_x, new_n_y, n_rect[2], n_rect[3])
                new_blocks[n_idx] = new_n

            rule_comp = rule_companions[i]
            if rule_comp is not None:
                r_idx, r_rect = rule_comp
                anchor_rect = anchor_rects[i]
                if anchor_rect is not None:
                    rdy = r_rect[1] - anchor_rect[1]
                    rdx = r_rect[0] - anchor_rect[0]
                else:
                    rdy = template_rule_offset[1] if template_rule_offset else 0
                    rdx = template_rule_offset[0] if template_rule_offset else 0
                new_r_y = new_anchor_y + rdy
                new_r_x = first_x + rdx
                new_blocks[r_idx] = _write_xfrm(
                    matches[r_idx].group(0), new_r_x, new_r_y, r_rect[2], r_rect[3]
                )
        else:
            anchor_clone = _replace_first_a_t(template_anchor_block, text)
            anchor_clone = _write_xfrm(
                anchor_clone, first_x, new_anchor_y, first_w, item_h
            )
            anchor_clone = _ensure_autofit_on_block(anchor_clone)
            appended_clones.append(anchor_clone)
            if template_number_block is not None and template_number_offset is not None:
                dx, dy, nw, nh = template_number_offset
                num_clone = _replace_first_a_t(template_number_block, f"{i + 1:02d}")
                num_clone = _write_xfrm(
                    num_clone, first_x + dx, new_anchor_y + dy, nw, nh
                )
                appended_clones.append(num_clone)
            if template_rule_block is not None and template_rule_offset is not None:
                rdx, rdy, rw, rh = template_rule_offset
                rule_clone = _write_xfrm(
                    template_rule_block,
                    first_x + rdx,
                    new_anchor_y + rdy,
                    rw,
                    rh,
                )
                appended_clones.append(rule_clone)

    for k in range(len(items), len(anchor_indices)):
        drop_indices.add(anchor_indices[k])
        comp = number_companions[k]
        if comp is not None:
            drop_indices.add(comp[0])
        rule_comp = rule_companions[k]
        if rule_comp is not None:
            drop_indices.add(rule_comp[0])

    # Step 5: stitch the slide XML back together.
    last_used_idx = (
        anchor_indices[min(len(items), len(anchor_indices)) - 1]
        if anchor_indices
        else 0
    )
    pieces: list[str] = []
    cursor = 0
    for i, m in enumerate(matches):
        pieces.append(slide_xml[cursor:m.start()])
        if i in drop_indices:
            pass
        elif i in new_blocks:
            pieces.append(new_blocks[i])
        else:
            pieces.append(m.group(0))
        if i == last_used_idx and appended_clones:
            pieces.append("\n".join(appended_clones))
        cursor = m.end()
    pieces.append(slide_xml[cursor:])

    return "".join(pieces)


def _replace_toc_items_textonly(slide_xml: str, items: list[str]) -> str:
    """Older fallback: just rewrite the text in each "項目タイトル" shape
    in document order, no geometry adjustment. Used when the template
    doesn't expose <a:xfrm> on the slot shapes."""
    i = 0

    def _rep(match: re.Match) -> str:
        nonlocal i
        block = match.group(0)
        text = _sp_text(block)
        if "項目タイトル" not in text:
            return block
        if i >= len(items):
            return ""
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
        if text.strip() in _BODY_PROMPT_EXACT_PATTERNS:
            return ""
        return block

    return _SP_BLOCK_RE.sub(_keep, slide_xml)


_PAGE_COUNTER_RE = re.compile(r"<a:t>\s*(\d{1,3})\s*/\s*(\d{1,3})\s*</a:t>")
_SECTION_NUMBER_RE = re.compile(
    r"<a:t>\s*(SECTION|Section|section)(\s+)(\d{1,3})\s*</a:t>"
)


def _replace_page_counter(slide_xml: str, current: int, total: int) -> str:
    """Rewrite ``<a:t>NN / MM</a:t>`` page-counter strings to the actual
    ``current / total`` of the rendered deck.

    Templates ship with a fixed counter like "04 / 06" baked into the
    slide footer. After we expand the deck to N slides, every slide
    keeps showing "/ 06" unless we rewrite it here. The regex matches
    only `<a:t>` content shaped exactly like ``<digits> / <digits>``,
    so legitimate body text containing slashes is never touched.

    Both numbers are zero-padded to two digits to match the template's
    formatting convention.
    """
    replacement = f"<a:t>{current:02d} / {total:02d}</a:t>"

    def _rep(_m: re.Match) -> str:
        return replacement

    return _PAGE_COUNTER_RE.sub(_rep, slide_xml)


def _replace_section_number(slide_xml: str, section_index: int) -> str:
    """Rewrite the section-divider label "SECTION NN" to reflect the
    actual section this divider marks.

    Templates ship the label with a fixed "SECTION  01" string baked
    into the slide XML. When a deck has multiple section dividers, we
    need the label to count up — 01 / 02 / 03 — or every divider
    still reads "01" in the rendered PPTX. The regex preserves the
    original whitespace between the keyword and the digits so the
    two-space convention the DXDesignSystem template uses survives.
    """

    def _rep(m: re.Match) -> str:
        keyword = m.group(1)
        gap = m.group(2)
        return f"<a:t>{keyword}{gap}{section_index:02d}</a:t>"

    return _SECTION_NUMBER_RE.sub(_rep, slide_xml)


def _detect_body_rect(slide_xml: str) -> tuple[int, int, int, int] | None:
    """Find the body area by reading the rect off the largest body-prompt
    decoration shape in the slide.

    Many real-world templates don't use <p:ph type="body">. They mark
    the body area with a styled text box that contains a prompt like
    "本文 ／ 図版 ／ 表をここに配置". The shape's <a:xfrm> is the
    actual body container; reading it lets the renderer position
    figures correctly without the user having to switch to a "proper"
    placeholder template, and without us having to guess body
    coordinates from slide dimensions alone.

    Returns (x, y, cx, cy) for the largest matching shape by area, or
    None when no body prompt shape is present.
    """
    candidates: list[tuple[int, int, int, int]] = []
    for m in _SP_BLOCK_RE.finditer(slide_xml):
        block = m.group(0)
        text = _sp_text(block)
        if not any(p in text for p in _BODY_PROMPT_PATTERNS):
            continue
        # Skip the small "項目タイトル" / "Section title" / "BODY"
        # auxiliary prompts — they're not the body container.
        if "項目タイトル" in text or "Section title" in text:
            continue
        rect = _read_xfrm(block)
        if rect is None:
            continue
        candidates.append(rect)
    if not candidates:
        return None
    return max(candidates, key=lambda r: r[2] * r[3])


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
