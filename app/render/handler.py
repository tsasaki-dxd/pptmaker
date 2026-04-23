"""
Lambda Container entrypoint for the Render service.

Event shape (from SQS or direct invoke):
{
  "job_id": "uuid",
  "tenant_id": "...",
  "project_id": "...",
  "template_s3": "s3://bucket/tenants/t/templates/tp_id.pptx",
  "blueprint": {...},
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3

from .db_status import update_project_status
from .layout_renderer import RenderRequest, render_content_slide
from .pptx_assembler import (
    assign_default_template_indices,
    derive_slides,
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
    poll ProjectRow.status to know when the deck is actually ready."""
    try:
        result = _process_job(job)
        update_project_status(job.project_id, "complete")
        return result
    except Exception:
        update_project_status(job.project_id, "failed")
        raise


def _parse_job(payload: dict[str, Any]) -> RenderJob:
    return RenderJob(
        job_id=payload["job_id"],
        tenant_id=payload["tenant_id"],
        project_id=payload["project_id"],
        template_s3=payload["template_s3"],
        blueprint=payload["blueprint"],
        out_prefix=payload["out_prefix"],
    )


def _process_job(job: RenderJob) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="slideforge-") as td:
        work = Path(td)

        tpl_local = work / "template.pptx"
        _download(job.template_s3, tpl_local)

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
            try:
                xmls[i - 1] = render_content_slide(
                    src_xml, req, start_shape_id=1000 + 100 * i
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

        out_pptx = work / "output.pptx"
        repack(unpacked, out_pptx)

        pptx_key = f"{job.out_prefix.rstrip('/')}/output.pptx"
        _upload(out_pptx, pptx_key)

        # Convert once to PDF and upload both the PDF itself (for the
        # "export as PDF" button) and per-slide JPEGs for the previews.
        pdf_key: str | None = None
        preview_keys: list[str] = []
        try:
            pdf_path = pptx_to_pdf(out_pptx, work / "preview")
            pdf_key = f"{job.out_prefix.rstrip('/')}/output.pdf"
            _upload(pdf_path, pdf_key)

            jpegs = pdf_to_jpegs(pdf_path, work / "preview" / "jpeg")
            for idx, jpg in enumerate(jpegs, start=1):
                key = f"{job.out_prefix.rstrip('/')}/preview/slide-{idx:02d}.jpg"
                _upload(jpg, key)
                preview_keys.append(key)
        except Exception:
            log.exception("pdf/preview generation failed for job=%s", job.job_id)

        return {
            "job_id": job.job_id,
            "pptx": pptx_key,
            "pdf": pdf_key,
            "previews": preview_keys,
            "slide_count": len(xmls),
            "template_pages_used": chosen,
            "skipped_slides": skipped,
        }


def _download(s3_uri: str, dest: Path) -> None:
    parsed = urlparse(s3_uri)
    s3.download_file(parsed.netloc, parsed.path.lstrip("/"), str(dest))


def _upload(src: Path, s3_uri: str) -> None:
    parsed = urlparse(s3_uri)
    s3.upload_file(str(src), parsed.netloc, parsed.path.lstrip("/"))
