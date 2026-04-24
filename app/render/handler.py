"""
Lambda Container entrypoint for the Render service.

Event shape (from SQS or direct invoke):
{
  "job_id": "uuid",
  "tenant_id": "...",
  "project_id": "...",
  "template_s3": "s3://bucket/tenants/t/templates/tp_id.pptx",
  "blueprint": {...},
  "template_layouts": [{"index": 1, "slots": [...], ...}, ...],
  "out_prefix": "s3://bucket/tenants/t/projects/p/outputs/v1/"
}

The handler downloads the template, renders each slide per the blueprint,
re-packs into a .pptx, generates JPEG previews via LibreOffice, and uploads
everything to S3.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3

from .db_status import update_project_status
from .layout_renderer import RenderRequest, render_content_slide
from .media import MediaRegistry
from .pptx_assembler import (
    assign_default_template_indices,
    derive_slides,
    finalize_media,
    read_template_slides,
    rewrite_content_types,
    rewrite_presentation_rels,
    rewrite_presentation_xml,
    write_output_slides,
)
from .preview import pdf_to_jpegs, pptx_to_pdf
from .template_loader import repack, safe_unpack

log = logging.getLogger("slideforge.render")
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

s3 = boto3.client("s3")


@dataclass
class RenderJob:
    job_id: str
    tenant_id: str
    project_id: str
    template_s3: str
    blueprint: dict[str, Any]
    out_prefix: str
    template_layouts: list[dict[str, Any]] = field(default_factory=list)
    design_tokens: dict[str, Any] = field(default_factory=dict)


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    start = time.time()

    if "Records" in event:  # SQS batch
        results = []
        for record in event["Records"]:
            job = _parse_job(json.loads(record["body"]))
            results.append(_run(job))
        return {"jobs": results}

    job = _parse_job(event)
    result = _run(job)
    log.info("render complete job=%s elapsed_ms=%d", job.job_id, int((time.time() - start) * 1000))
    return result


def _run(job: RenderJob) -> dict[str, Any]:
    """Wrap _process_job with project status write-back so the UI can
    poll ProjectRow.status to know when the deck is actually ready.

    Status values:
      - complete: pptx, pdf, and slide previews all in S3
      - partial:  pptx uploaded but the pdf/preview step failed
                  (usually LibreOffice). User can still download the
                  pptx; preview / .pdf buttons won't work.
      - failed:   didn't even get to a pptx upload
    """
    try:
        result = _process_job(job)
    except Exception:
        update_project_status(job.project_id, "failed")
        raise
    if result.get("preview_error"):
        update_project_status(job.project_id, "partial")
    else:
        update_project_status(job.project_id, "complete")
    return result


def _parse_job(payload: dict[str, Any]) -> RenderJob:
    return RenderJob(
        job_id=payload["job_id"],
        tenant_id=payload["tenant_id"],
        project_id=payload["project_id"],
        template_s3=payload["template_s3"],
        blueprint=payload["blueprint"],
        out_prefix=payload["out_prefix"],
        template_layouts=list(payload.get("template_layouts") or []),
        design_tokens=dict(payload.get("design_tokens") or {}),
    )


def _slide_size_from_tokens(
    design_tokens: dict[str, Any],
) -> tuple[int, int] | None:
    entry = design_tokens.get("slide_size") if design_tokens else None
    if not isinstance(entry, dict):
        return None
    cx = entry.get("cx_emu")
    cy = entry.get("cy_emu")
    if not isinstance(cx, int) or not isinstance(cy, int):
        return None
    if cx <= 0 or cy <= 0:
        return None
    return cx, cy


def _process_job(job: RenderJob) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="slideforge-") as td:
        work = Path(td)

        tpl_local = work / "template.pptx"
        _download(job.template_s3, tpl_local)

        # Read the template bytes ONCE for theme inheritance. Reused
        # across every slide so we don't re-download per-slide.
        theme_bytes = _read_template_bytes(tpl_local)

        unpacked = safe_unpack(tpl_local, work / "unpacked")

        # Snapshot the template's original slide files before we wipe
        # them — many output slides may derive from one template slide
        # (intentional; that's how a 6-page template fills a 20-slide
        # blueprint).
        template_slides = read_template_slides(unpacked.root)
        if not template_slides:
            raise RuntimeError("template has no slide files (ppt/slides/slide*.xml)")
        template_slide_count = max(template_slides.keys())

        blueprint_slides = job.blueprint.get("slides", [])
        if not blueprint_slides:
            raise RuntimeError("blueprint has no slides")

        chosen = assign_default_template_indices(blueprint_slides, template_slide_count)
        xmls, rels = derive_slides(template_slides, chosen)

        layout_by_index = _index_layouts(job.template_layouts)
        registry = MediaRegistry()
        slide_size = _slide_size_from_tokens(job.design_tokens)

        skipped: list[int] = []
        for i, (slide, src_xml) in enumerate(
            zip(blueprint_slides, xmls, strict=True), start=1
        ):
            req = RenderRequest(
                slide_index=i,
                layout=slide.get("layout", "content"),
                figure_type=slide.get("figure_type"),
                content=slide.get("content", {}),
            )
            layout_entry = layout_by_index.get(chosen[i - 1]) or {}
            slots = list(layout_entry.get("slots") or [])
            try:
                xmls[i - 1] = render_content_slide(
                    src_xml,
                    req,
                    start_shape_id=1000 + 100 * i,
                    slots=slots,
                    theme_pptx_bytes=theme_bytes,
                    slide_size=slide_size,
                    total_slides=len(blueprint_slides),
                )
            except Exception:
                # Leave the unmodified template XML in place for this
                # slide so the user still gets a deck, log loud enough
                # to investigate.
                log.exception(
                    "render failed for slide %d (figure=%s); using template page %d unmodified",
                    i,
                    req.figure_type,
                    chosen[i - 1],
                )
                skipped.append(i)

        # Replace the slide files and the package metadata that points
        # at them. Order matters: write slide files first, then the
        # presentation/rels/content-types so they reference real files.
        write_output_slides(unpacked.root, xmls, rels)
        rewrite_presentation_xml(unpacked.root, len(xmls))
        rewrite_presentation_rels(unpacked.root, len(xmls))
        rewrite_content_types(unpacked.root, len(xmls))

        media_warnings = finalize_media(
            unpacked.root, registry, _storage_download_bytes
        )
        if media_warnings:
            log.warning("finalize_media warnings: %s", media_warnings)

        out_pptx = work / "output.pptx"
        repack(unpacked, out_pptx)

        pptx_key = f"{job.out_prefix.rstrip('/')}/output.pptx"
        _upload(out_pptx, pptx_key)

        # Convert once to PDF and upload both the PDF itself (for the
        # "export as PDF" button) and per-slide JPEGs for the previews.
        pdf_key: str | None = None
        preview_keys: list[str] = []
        preview_error: str | None = None
        try:
            pdf_path = pptx_to_pdf(out_pptx, work / "preview")
            pdf_key = f"{job.out_prefix.rstrip('/')}/output.pdf"
            _upload(pdf_path, pdf_key)

            jpegs = pdf_to_jpegs(pdf_path, work / "preview" / "jpeg")
            for idx, jpg in enumerate(jpegs, start=1):
                key = f"{job.out_prefix.rstrip('/')}/preview/slide-{idx:02d}.jpg"
                _upload(jpg, key)
                preview_keys.append(key)
        except Exception as e:
            # Keep the pptx upload (it's already in S3 and usable), but
            # record the failure so _run() can set project.status to
            # "partial" instead of lying about full success.
            log.exception("pdf/preview generation failed for job=%s", job.job_id)
            preview_error = str(e)

        return {
            "job_id": job.job_id,
            "pptx": pptx_key,
            "pdf": pdf_key,
            "previews": preview_keys,
            "slide_count": len(xmls),
            "template_pages_used": chosen,
            "skipped_slides": skipped,
            "preview_error": preview_error,
        }


def _download(s3_uri: str, dest: Path) -> None:
    parsed = urlparse(s3_uri)
    s3.download_file(parsed.netloc, parsed.path.lstrip("/"), str(dest))


def _read_template_bytes(path: Path) -> bytes | None:
    """Read the downloaded template once so theme inheritance can reuse
    it across every slide without re-downloading."""
    try:
        return path.read_bytes()
    except OSError:
        log.warning("could not read template bytes from %s", path, exc_info=True)
        return None


def _index_layouts(
    layouts: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """Build a {template_slide_index -> layout_entry} map.

    Accepts either ``source_slide_index`` (preferred per Phase 2.x) or
    the older ``index`` key.
    """
    out: dict[int, dict[str, Any]] = {}
    for entry in layouts or []:
        idx = entry.get("source_slide_index")
        if not isinstance(idx, int):
            idx = entry.get("index")
        if isinstance(idx, int):
            out[idx] = entry
    return out


def _storage_download_bytes(s3_key: str) -> bytes | None:
    """Local import wrapper for ``storage.download_bytes``.

    Deferred so the render container doesn't drag FastAPI settings into
    import time when the api module isn't installed at runtime.
    """
    from api.services.storage import download_bytes

    return download_bytes(s3_key)


# Browsers download instead of rendering inline when S3 serves an
# object as application/octet-stream, so preview JPEGs have to go up
# with explicit Content-Type. The .pptx one is about the user saving
# it with the right extension; without the header, the file ends up
# as "output.pptx" but .octet-stream and Windows / macOS get confused.
_CONTENT_TYPE_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def _upload(src: Path, s3_uri: str) -> None:
    parsed = urlparse(s3_uri)
    bucket, key = parsed.netloc, parsed.path.lstrip("/")
    ct = _CONTENT_TYPE_BY_EXT.get(src.suffix.lower())
    if ct:
        s3.upload_file(str(src), bucket, key, ExtraArgs={"ContentType": ct})
    else:
        s3.upload_file(str(src), bucket, key)
