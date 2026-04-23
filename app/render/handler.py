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

from .layout_renderer import RenderRequest, render_content_slide
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
            results.append(_process_job(job))
        return {"jobs": results}

    job = _parse_job(event)
    result = _process_job(job)
    log.info("render complete job=%s elapsed_ms=%d", job.job_id, int((time.time() - start) * 1000))
    return result


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

        skipped: list[int] = []
        for i, slide in enumerate(job.blueprint.get("slides", []), start=1):
            req = RenderRequest(
                slide_index=i,
                layout=slide.get("layout", "content"),
                figure_type=slide.get("figure_type"),
                content=slide.get("content", {}),
            )
            try:
                original_xml = unpacked.read_slide(i)
            except FileNotFoundError:
                log.warning("slide %d not found in template, skipping", i)
                continue
            try:
                new_xml = render_content_slide(original_xml, req, start_shape_id=1000 + 100 * i)
                unpacked.write_slide(i, new_xml)
            except Exception:
                # Don't kill the entire deck on one malformed slide. Log
                # and leave the template's original slide in place so the
                # user still gets something back.
                log.exception("render failed for slide %d (figure=%s); skipping", i, req.figure_type)
                skipped.append(i)

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
            "slide_count": len(job.blueprint.get("slides", [])),
            "skipped_slides": skipped,
        }


def _download(s3_uri: str, dest: Path) -> None:
    parsed = urlparse(s3_uri)
    s3.download_file(parsed.netloc, parsed.path.lstrip("/"), str(dest))


def _upload(src: Path, s3_uri: str) -> None:
    parsed = urlparse(s3_uri)
    s3.upload_file(str(src), parsed.netloc, parsed.path.lstrip("/"))
