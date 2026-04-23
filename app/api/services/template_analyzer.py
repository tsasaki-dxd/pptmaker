"""
Lightweight .pptx introspection for the API Lambda.

Now does two things: counts slides (so the UI dropdown has the right
number of options) and runs the rule-based layout classifier from
template_registry so default blueprint → template page mapping can
match by type instead of blindly cycling.
"""

from __future__ import annotations

import io
import logging
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import boto3

from .template_registry import classify_layouts

log = logging.getLogger("slideforge.template_analyzer")


@dataclass
class TemplateAnalysis:
    slide_count: int
    # [{"index": 1, "layout": "cover", "confidence": 0.95, "reason": "..."}, ...]
    layouts: list[dict]


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


def analyze_template(s3_uri: str) -> TemplateAnalysis | None:
    """Download + count + classify. Returns None if the fetch fails."""
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

    # classify_layouts walks the zip itself — simplest to give it a
    # file on disk. The .pptx is small (KB range).
    layouts: list[dict] = []
    try:
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=True) as tmp:
            tmp.write(body)
            tmp.flush()
            for c in classify_layouts(Path(tmp.name)):
                layouts.append(
                    {
                        "index": c.slide_index,
                        "layout": c.layout,
                        "confidence": c.confidence,
                        "reason": c.reason,
                    }
                )
    except Exception:
        log.exception("classify_layouts failed for %s", s3_uri)

    return TemplateAnalysis(slide_count=slide_count, layouts=layouts)


def count_template_slides(s3_uri: str) -> int:
    """Back-compat shim: just the count. Prefer analyze_template for new callers."""
    a = analyze_template(s3_uri)
    return a.slide_count if a else 0
