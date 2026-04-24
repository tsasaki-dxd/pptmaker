"""
Lightweight .pptx introspection for the API Lambda.

Now does three things: counts slides (so the UI dropdown has the right
number of options), runs the rule-based layout classifier from
template_registry so default blueprint → template page mapping can
match by type instead of blindly cycling, and extracts per-slide slot
metadata (Phase 2 design §4.2) so downstream blueprint generation can
reason about placeholders without re-parsing the .pptx.
"""

from __future__ import annotations

import io
import logging
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3

from render.slot_extractor import (
    EMURect,
    FixedElement,
    Slot,
    SlotExtractionError,
    extract_slots,
)

from .template_registry import classify_layouts

log = logging.getLogger("slideforge.template_analyzer")


_DEFAULT_SLIDE_SIZE_16_9: dict[str, int] = {"cx_emu": 12192000, "cy_emu": 6858000}


@dataclass
class TemplateAnalysis:
    slide_count: int
    # [{"index": 1, "layout": "cover", "confidence": 0.95, "reason": "...",
    #   "slots": [...], "fixed_elements": [...]}, ...]
    layouts: list[dict]
    design_tokens: dict[str, Any] = field(default_factory=dict)


def _fetch_pptx(s3_uri: str) -> bytes | None:
    parsed = urlparse(s3_uri)
    if parsed.scheme != "s3":
        log.warning("not an s3:// uri: %s", s3_uri)
        return None
    try:
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
        return obj["Body"].read()
    except Exception:
        log.exception("could not fetch %s", s3_uri)
        return None


def _rect_to_dict(rect: EMURect | None) -> dict[str, int] | None:
    if rect is None:
        return None
    return {"x": rect.x, "y": rect.y, "cx": rect.cx, "cy": rect.cy}


def _slot_to_dict(slot: Slot) -> dict[str, Any]:
    # Flat x/y/w/h keys to match layout_renderer._slot_to_box expectations.
    # See template_registry._slot_to_dict for the history note.
    out: dict[str, Any] = {
        "id": slot.id,
        "kind": slot.kind,
        "role": slot.role,
        "idx": slot.idx,
    }
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


def _extract_slide_size(pptx_bytes: bytes) -> tuple[int, int] | None:
    """Parse ``ppt/presentation.xml`` and return ``(cx_emu, cy_emu)``.

    Returns None if the entry is missing, the XML is malformed, or the
    ``<p:sldSz>`` element / its ``cx``/``cy`` attributes are absent.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(pptx_bytes)) as zf:
            try:
                xml = zf.read("ppt/presentation.xml")
            except KeyError:
                return None
    except (zipfile.BadZipFile, OSError):
        return None
    m = re.search(rb"<p:sldSz\b([^/>]*)/?>", xml)
    if not m:
        return None
    attrs = m.group(1)
    cx_match = re.search(rb'cx="(\d+)"', attrs)
    cy_match = re.search(rb'cy="(\d+)"', attrs)
    if not cx_match or not cy_match:
        return None
    try:
        cx = int(cx_match.group(1))
        cy = int(cy_match.group(1))
    except ValueError:
        return None
    if cx <= 0 or cy <= 0:
        return None
    return cx, cy


def _extract_slot_metadata(body: bytes) -> dict[int, dict[str, list[dict[str, Any]]]]:
    """Map slide_index (1-based) -> {"slots": [...], "fixed_elements": [...]}.

    A per-slide SlotExtractionError is logged and replaced with empty lists;
    it does not abort the whole template.
    """
    meta: dict[int, dict[str, list[dict[str, Any]]]] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            slide_names = sorted(
                n for n in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)
            )
            for idx, name in enumerate(slide_names, start=1):
                slide_xml = zf.read(name)
                try:
                    result = extract_slots(slide_xml)
                    meta[idx] = {
                        "slots": [_slot_to_dict(s) for s in result.slots],
                        "fixed_elements": [_fixed_to_dict(f) for f in result.fixed],
                    }
                except SlotExtractionError as e:
                    log.warning("slot extraction failed for %s: %s", name, e)
                    meta[idx] = {"slots": [], "fixed_elements": []}
    except Exception:
        log.exception("could not walk pptx for slot extraction")
    return meta


def analyze_template(s3_uri: str) -> TemplateAnalysis | None:
    """Download + count + classify + extract slots. Returns None if the fetch fails."""
    body = _fetch_pptx(s3_uri)
    if body is None:
        return None

    try:
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            names = zf.namelist()
        slide_count = sum(
            1
            for n in names
            if n.startswith("ppt/slides/slide") and n.endswith(".xml")
            and "/_rels/" not in n
        )
    except Exception:
        log.exception("could not parse pptx zip from %s", s3_uri)
        return None

    slot_meta = _extract_slot_metadata(body)

    # classify_layouts walks the zip itself — simplest to give it a
    # file on disk. The .pptx is small (KB range).
    layouts: list[dict] = []
    try:
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=True) as tmp:
            tmp.write(body)
            tmp.flush()
            for c in classify_layouts(Path(tmp.name)):
                entry = slot_meta.get(c.slide_index, {"slots": [], "fixed_elements": []})
                layouts.append(
                    {
                        "index": c.slide_index,
                        "layout": c.layout,
                        "confidence": c.confidence,
                        "reason": c.reason,
                        "slots": entry["slots"],
                        "fixed_elements": entry["fixed_elements"],
                    }
                )
    except Exception:
        log.exception("classify_layouts failed for %s", s3_uri)

    size = _extract_slide_size(body)
    if size is None:
        log.debug("slide size not found in %s; defaulting to 16:9", s3_uri)
        slide_size_tokens = dict(_DEFAULT_SLIDE_SIZE_16_9)
    else:
        slide_size_tokens = {"cx_emu": size[0], "cy_emu": size[1]}
    design_tokens: dict[str, Any] = {"slide_size": slide_size_tokens}

    return TemplateAnalysis(
        slide_count=slide_count,
        layouts=layouts,
        design_tokens=design_tokens,
    )


def count_template_slides(s3_uri: str) -> int:
    """Back-compat shim: just the count. Prefer analyze_template for new callers."""
    a = analyze_template(s3_uri)
    return a.slide_count if a else 0
