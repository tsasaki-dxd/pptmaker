"""
Lightweight .pptx introspection for the API Lambda.

Right now we only need the slide count (so the UI can populate the
per-slide template-page dropdown), but this is the natural home for
future template metadata extraction (master/layout names, theme colors,
etc.).
"""

from __future__ import annotations

import io
import logging
import zipfile
from urllib.parse import urlparse

import boto3

log = logging.getLogger("slideforge.template_analyzer")


def count_template_slides(s3_uri: str) -> int:
    """Download the .pptx (a zip) and count ppt/slides/slide*.xml entries.

    Returns 0 on any failure — we'd rather a missing analysis make the
    dropdown a no-op than block template viewing entirely.
    """
    parsed = urlparse(s3_uri)
    if parsed.scheme != "s3":
        log.warning("not an s3:// uri: %s", s3_uri)
        return 0
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")

    try:
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()
    except Exception:
        log.exception("could not fetch %s", s3_uri)
        return 0

    try:
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            names = zf.namelist()
        # ppt/slides/slide1.xml, slide2.xml, ... — exclude the _rels/ subdir.
        slide_xmls = [
            n for n in names
            if n.startswith("ppt/slides/slide") and n.endswith(".xml")
            and "/_rels/" not in n
        ]
        return len(slide_xmls)
    except Exception:
        log.exception("could not parse pptx zip from %s", s3_uri)
        return 0
