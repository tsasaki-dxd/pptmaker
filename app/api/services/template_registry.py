"""
Template parsing: layout classification + design-token extraction.

Phase 1 uses rule-based classification (see docs/04_template_and_plugin.md
§3). LLM-based fallback is TODO for Phase 2.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from render.slot_extractor import (
    EMURect,
    FixedElement,
    Slot,
    SlotExtractionError,
    extract_slots,
)

if TYPE_CHECKING:
    from api.models.schemas import TemplateProfile

log = logging.getLogger("slideforge.template")

LAYOUT_TAGS = ("cover", "toc", "section_divider", "content", "about", "disclaimer")


@dataclass
class LayoutClassification:
    slide_index: int
    layout: str
    confidence: float
    reason: str


def classify_layouts(pptx_path: Path) -> list[LayoutClassification]:
    """Run rule-based layout classification over slides 1..N."""
    results: list[LayoutClassification] = []
    with zipfile.ZipFile(pptx_path) as zf:
        slide_names = sorted(n for n in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n))
        for idx, name in enumerate(slide_names, start=1):
            xml = zf.read(name).decode("utf-8", errors="ignore")
            label, conf, reason = _classify_slide(idx, xml, total=len(slide_names))
            results.append(
                LayoutClassification(slide_index=idx, layout=label, confidence=conf, reason=reason)
            )
    return results


def _classify_slide(index: int, xml: str, total: int) -> tuple[str, float, str]:
    text_runs = re.findall(r"<a:t>([^<]*)</a:t>", xml)
    joined = "".join(text_runs)

    if index == 1:
        return ("cover", 0.95, "first slide -> cover")
    if index == 2 and any("目次" in t or "Contents" in t for t in text_runs):
        return ("toc", 0.9, "title contains toc marker")
    if index == total and any(
        any(k in t for k in ("免責", "Disclaimer", "注意事項")) for t in text_runs
    ):
        return ("disclaimer", 0.85, "disclaimer keyword found")
    if any("会社概要" in t or "About" in t for t in text_runs):
        return ("about", 0.8, "about keyword found")
    # Section divider cues: numeric markers ("1.", "01"), or explicit
    # labels the template designer uses for chapter/section pages.
    # Corporate decks commonly brand these as "SECTION 01" / "セクション"
    # / "第N章" rather than plain "1." — the old heuristic missed all
    # of those and misclassified them as content, so section dividers
    # ended up being rendered onto content template pages.
    section_cue = any(
        re.search(r"\b[Ss][Ee][Cc][Tt][Ii][Oo][Nn]\b", t)
        or "セクション" in t
        or re.search(r"第\s*\d+\s*章", t)
        or re.search(r"\bChapter\b", t)
        for t in text_runs
    )
    if (
        re.search(r"^\s*0?\d\s*$", joined)
        or any(re.match(r"\d{1,2}\.", t.strip()) for t in text_runs)
        or section_cue
    ):
        return ("section_divider", 0.7, "section marker")
    return ("content", 0.6, "default content")


def summarize_for_prompt(classifications: list[LayoutClassification]) -> str:
    """Compact template profile text passed to the blueprint LLM."""
    lines = [f"総スライド数: {len(classifications)}"]
    for c in classifications:
        lines.append(f"- slide{c.slide_index}: {c.layout} (信頼度 {c.confidence:.2f})")
    return "\n".join(lines)


def _rect_to_dict(rect: EMURect | None) -> dict[str, int] | None:
    if rect is None:
        return None
    return {"x": rect.x, "y": rect.y, "cx": rect.cx, "cy": rect.cy}


def _slot_to_dict(slot: Slot) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": slot.id,
        "kind": slot.kind,
        "role": slot.role,
        "idx": slot.idx,
    }
    # Flatten rect into x/y/w/h at the top level so layout_renderer's
    # _slot_to_box / _render_text_slot / _pick_figure_slot can read
    # them directly. A previous version nested the rect under "rect"
    # with cx/cy keys, which didn't match what the render side reads,
    # so FF_SLOT_RENDER paths crashed with KeyError on every slide and
    # the handler silently fell back to the unmodified template —
    # leaving placeholder text bleeding through.
    if slot.rect is not None:
        out["x"] = slot.rect.x
        out["y"] = slot.rect.y
        out["w"] = slot.rect.cx
        out["h"] = slot.rect.cy
    return out


def _fixed_to_dict(fixed: FixedElement) -> dict[str, Any]:
    out: dict[str, Any] = {"element_type": fixed.element_type}
    if fixed.rect is not None:
        out["x"] = fixed.rect.x
        out["y"] = fixed.rect.y
        out["w"] = fixed.rect.cx
        out["h"] = fixed.rect.cy
    return out


def _layout_has_slots(layout: dict[str, Any]) -> bool:
    if "slots" not in layout or "fixed_elements" not in layout:
        return False
    # Detect the legacy nested-rect format and force re-extraction so
    # existing templates get rewritten into the flat format above.
    slots = layout["slots"]
    if slots:
        first = slots[0]
        if not isinstance(first, dict) or ("w" not in first and first.get("rect") is not None):
            return False
    return True


def _read_slide_xml(zf: zipfile.ZipFile, slide_index: int) -> bytes | None:
    name = f"ppt/slides/slide{slide_index}.xml"
    try:
        return zf.read(name)
    except KeyError:
        return None


def ensure_slots_populated(
    profile: TemplateProfile,
    pptx_fetcher: Callable[[str], bytes | None],
) -> TemplateProfile:
    """Lazy-migrate pre-Phase-2 TemplateProfile rows to include slot metadata.

    Fast path: if every layout already has `slots` and `fixed_elements`, return
    the profile unchanged without calling the fetcher.

    Slow path: fetch the template .pptx bytes and re-run slot extraction for
    each layout whose `source_slide_index` is set but slot keys are missing.
    The returned profile is a new instance (model_copy) — the input is not
    mutated. Persistence is the caller's responsibility.
    """
    layouts = profile.layouts
    if all(_layout_has_slots(lo) for lo in layouts):
        return profile

    body = pptx_fetcher(profile.original_s3_path)
    if body is None:
        log.warning(
            "cannot lazy-migrate slots for template %s: pptx_fetcher returned None",
            profile.id,
        )
        return profile

    try:
        zf = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile as e:
        log.warning(
            "cannot lazy-migrate slots for template %s: malformed pptx (%s)",
            profile.id,
            e,
        )
        return profile

    new_layouts: list[dict[str, Any]] = []
    try:
        with zf:
            for layout in layouts:
                if _layout_has_slots(layout):
                    new_layouts.append(layout)
                    continue

                idx = layout.get("source_slide_index")
                if idx is None:
                    idx = layout.get("index")
                if not isinstance(idx, int):
                    new_layouts.append({**layout, "slots": [], "fixed_elements": []})
                    continue

                slide_xml = _read_slide_xml(zf, idx)
                if slide_xml is None:
                    log.warning(
                        "template %s slide %d missing from pptx; leaving slots empty",
                        profile.id,
                        idx,
                    )
                    new_layouts.append({**layout, "slots": [], "fixed_elements": []})
                    continue

                try:
                    result = extract_slots(slide_xml)
                    new_layouts.append(
                        {
                            **layout,
                            "slots": [_slot_to_dict(s) for s in result.slots],
                            "fixed_elements": [_fixed_to_dict(f) for f in result.fixed],
                        }
                    )
                except SlotExtractionError as e:
                    log.warning(
                        "slot extraction failed for template %s slide %d: %s",
                        profile.id,
                        idx,
                        e,
                    )
                    new_layouts.append({**layout, "slots": [], "fixed_elements": []})
    except Exception:
        log.warning(
            "unexpected error during lazy slot migration for template %s",
            profile.id,
            exc_info=True,
        )
        return profile

    return profile.model_copy(update={"layouts": new_layouts})
