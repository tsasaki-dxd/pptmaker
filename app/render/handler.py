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
from .layout_designer import _designer_enabled, design_layout
from .layout_renderer import RenderRequest, render_content_slide
from .layout_spec import emit_layout_spec
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
from .template_meta import load_template_meta

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


def _build_designer_llm() -> Any | None:
    """Construct an Anthropic SDK client. Returns ``None`` when
    Anthropic isn't installed (unit-test environments) or no API key
    is reachable; the render path falls back silently.
    """
    try:
        from anthropic import Anthropic
    except Exception:
        log.exception("anthropic SDK unavailable; layout designer disabled")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        secret_name = os.environ.get("ANTHROPIC_API_KEY_SECRET")
        if secret_name:
            try:
                sm = boto3.client(
                    "secretsmanager",
                    region_name=os.environ.get("AWS_REGION", "ap-northeast-1"),
                )
                api_key = sm.get_secret_value(SecretId=secret_name)["SecretString"]
            except Exception:
                log.exception(
                    "failed to fetch Anthropic API key from secret %s; "
                    "layout designer disabled",
                    secret_name,
                )
                return None
    if not api_key:
        log.warning("no Anthropic API key available; layout designer disabled")
        return None

    try:
        return Anthropic(api_key=api_key)
    except Exception:
        log.exception("Anthropic client init failed; layout designer disabled")
        return None


def _resolve_template_meta(job: RenderJob) -> Any | None:
    """Locate the curated template metadata (if any) for this render
    job. ``design_tokens.template_id`` wins; otherwise fall back to
    the first template id we have a JSON for so v1 single-template
    deploys "just work" without explicit configuration.
    """
    template_id = None
    if isinstance(job.design_tokens, dict):
        template_id = job.design_tokens.get("template_id")
    if not template_id:
        # v1 fallback: assume DXDesignSystem when nothing better is
        # available (the only template currently shipped).
        template_id = "dxdesignsystem"
    return load_template_meta(template_id)


# Max concurrent designer calls. Anthropic's Tier 1 rate limit is
# around 50 RPM for Sonnet — 8 concurrent comfortably stays under
# that even with the 5-15s per-call duration we've seen.
_DESIGNER_MAX_CONCURRENCY = 8

# Only content-layout slides get handed to the layout-designer LLM.
# Cover / toc / section_divider / about / disclaimer are structural
# pages whose deterministic rendering already matches the template —
# running an LLM over them just burns cost and latency for no visible
# change, and risks the designer producing shapes that conflict with
# the template's own decoration on those pages.
_DESIGNER_ELIGIBLE_LAYOUTS: frozenset[str] = frozenset({"content"})


def _submit_designer_batch(
    *,
    blueprint_slides: list[dict[str, Any]],
    template_meta: Any | None,
    designer_llm: Any | None,
) -> dict[int, Any]:
    """Kick off designer calls for every eligible slide in parallel
    and return a ``{slide_index_1based: Future[LayoutSpec | None]}``
    map. Slides with no body_box (cover/about/disclaimer/etc.) are
    mapped to an immediately-resolved None so the render loop's
    lookup stays uniform.

    Parallelism matters: 16 serial calls at 10s each = 160s just for
    LLM, on top of ~60s deterministic render time, overshoots the
    5-minute Lambda timeout. ThreadPoolExecutor collapses the wait
    to roughly the slowest single call.
    """
    from concurrent.futures import Future, ThreadPoolExecutor

    futures: dict[int, Any] = {}
    if designer_llm is None or template_meta is None:
        return futures

    executor = ThreadPoolExecutor(
        max_workers=_DESIGNER_MAX_CONCURRENCY,
        thread_name_prefix="designer",
    )

    for i, slide in enumerate(blueprint_slides, start=1):
        layout = slide.get("layout", "content")
        page_meta = template_meta.page_for(layout)
        # Skip unless the layout is explicitly designer-eligible AND
        # the template exposes a body_box for it. Either check alone
        # would let one misconfiguration (layout typo, stray body_box
        # in the wrong page entry) accidentally route template-
        # decoration pages through the LLM.
        eligible = (
            layout in _DESIGNER_ELIGIBLE_LAYOUTS
            and page_meta is not None
            and page_meta.body_box is not None
        )
        if not eligible:
            # Pre-resolved None so the render loop doesn't have to
            # special-case "no future submitted for this slide".
            done: Future[Any] = Future()
            done.set_result(None)
            futures[i] = done
            continue
        body_rect = (
            page_meta.body_box.x_emu,
            page_meta.body_box.y_emu,
            page_meta.body_box.w_emu,
            page_meta.body_box.h_emu,
        )
        futures[i] = executor.submit(
            design_layout,
            slide=slide,
            template_page_meta=page_meta.model_dump(mode="python"),
            body_rect=body_rect,
            llm=designer_llm,
        )

    # Let the executor keep running after we return; futures hold
    # their own references. Shutdown happens implicitly when the
    # last future is awaited.
    executor.shutdown(wait=False)
    return futures


def _collect_designer_result(
    futures: dict[int, Any], slide_index: int
) -> Any | None:
    """Block on the future for one slide and unwrap it. Any designer
    exception degrades to None (caller falls back to deterministic
    rendering) so one bad slide doesn't kill the deck."""
    fut = futures.get(slide_index)
    if fut is None:
        return None
    try:
        return fut.result(timeout=45)
    except Exception:
        log.exception("layout designer future failed for slide %d", slide_index)
        return None


def _emit_spec_if_any(
    spec: Any | None, *, start_shape_id: int
) -> list[str] | None:
    if spec is None:
        return None
    fragments, _next_id = emit_layout_spec(spec, start_shape_id=start_shape_id)
    return fragments


def _maybe_design_layout(
    *,
    slide: dict[str, Any],
    req: RenderRequest,
    src_xml: str,
    template_meta: Any | None,
    slide_size: tuple[int, int] | None,
    designer_llm: Any | None,
    start_shape_id: int,
) -> list[str] | None:
    """Serial-path designer call, kept for unit tests / single-slide
    entry points. The production render loop uses the batch form
    (_submit_designer_batch + _collect_designer_result) instead.
    """
    if designer_llm is None or template_meta is None:
        return None

    page_meta = template_meta.page_for(req.layout)
    if page_meta is None or page_meta.body_box is None:
        # No body box defined for this layout (e.g. cover/about/
        # disclaimer): designer doesn't apply, fall back to the
        # template-as-is.
        return None

    body_rect = (
        page_meta.body_box.x_emu,
        page_meta.body_box.y_emu,
        page_meta.body_box.w_emu,
        page_meta.body_box.h_emu,
    )

    spec = design_layout(
        slide=slide,
        template_page_meta=page_meta.model_dump(mode="python"),
        body_rect=body_rect,
        llm=designer_llm,
    )
    if spec is None:
        return None

    fragments, _next_id = emit_layout_spec(spec, start_shape_id=start_shape_id)
    return fragments


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

        # Optional layout-designer LLM. Only constructed when the flag
        # is on so render Lambdas without an Anthropic API key
        # configured don't try to import or hit the SDK.
        designer_llm = _build_designer_llm() if _designer_enabled() else None
        template_meta = _resolve_template_meta(job)

        # Kick off every designer call in parallel before the render
        # loop — each LLM call is 5-15s IO-bound, and serialising 16
        # of them blows past the Lambda's 5-minute timeout. A thread
        # pool (the SDK is synchronous per call but HTTP-bound so the
        # GIL isn't a bottleneck) collapses the total wait into
        # roughly the slowest single request.
        designer_futures = _submit_designer_batch(
            blueprint_slides=blueprint_slides,
            template_meta=template_meta,
            designer_llm=designer_llm,
        )

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

            spec = _collect_designer_result(designer_futures, i)
            extra_shapes_xml = _emit_spec_if_any(spec, start_shape_id=1000 + 100 * i)

            try:
                xmls[i - 1] = render_content_slide(
                    src_xml,
                    req,
                    start_shape_id=1000 + 100 * i,
                    slots=slots,
                    theme_pptx_bytes=theme_bytes,
                    slide_size=slide_size,
                    total_slides=len(blueprint_slides),
                    extra_shapes_xml=extra_shapes_xml,
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
