"""
Template parsing: layout classification + design-token extraction.

Phase 1 uses rule-based classification (see docs/04_template_and_plugin.md
§3). LLM-based fallback is TODO for Phase 2.
"""

from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

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
    if re.search(r"^\s*0?\d\s*$", joined) or any(re.match(r"\d{1,2}\.", t.strip()) for t in text_runs):
        return ("section_divider", 0.7, "section number marker")
    return ("content", 0.6, "default content")


def summarize_for_prompt(classifications: list[LayoutClassification]) -> str:
    """Compact template profile text passed to the blueprint LLM."""
    lines = [f"総スライド数: {len(classifications)}"]
    for c in classifications:
        lines.append(f"- slide{c.slide_index}: {c.layout} (信頼度 {c.confidence:.2f})")
    return "\n".join(lines)
