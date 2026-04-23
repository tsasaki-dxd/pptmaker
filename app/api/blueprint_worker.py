"""
SQS-driven Lambda handler for async blueprint generation.

Shares the api/ code bundle with the HTTP API Lambda. Same VPC, same
env vars; the difference is entry point + trigger. Each SQS record is
one blueprint job: load the BlueprintJobRow, call the LLM, write the
resulting BlueprintRow, flip status to "complete" or "failed".

Event source: the BlueprintQueue SQS queue (see infra/stacks/app_stack.py).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from uuid import uuid4

from .models.db import (
    BlueprintJobRow,
    BlueprintRow,
    ProjectRow,
    TemplateProfileRow,
    new_session,
)
from .services.blueprint_builder import BlueprintBuildError, build_blueprint
from .services.llm import LLMClient
from .services.template_analyzer import analyze_template

log = logging.getLogger("slideforge.blueprint_worker")
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    records = event.get("Records") or []
    if not records:
        log.warning("blueprint_worker invoked with non-SQS event; ignoring")
        return {"status": "noop"}

    for record in records:
        try:
            body = json.loads(record["body"])
        except Exception:
            log.exception("could not parse SQS record body")
            continue
        _process(body)

    return {"status": "ok", "count": len(records)}


def _process(msg: dict[str, Any]) -> None:
    job_id = msg.get("job_id")
    if not job_id:
        log.error("message missing job_id: %s", msg)
        return

    db = new_session()
    try:
        job = (
            db.query(BlueprintJobRow)
            .filter(BlueprintJobRow.id == job_id)
            .one_or_none()
        )
        if job is None:
            log.error("job %s not in DB; dropping", job_id)
            return
        if job.status != "pending":
            # Already processed, probably a redelivery. SQS at-least-once.
            log.info("job %s already status=%s; skipping", job_id, job.status)
            return

        project = (
            db.query(ProjectRow)
            .filter(ProjectRow.id == job.project_id)
            .one_or_none()
        )
        if project is None:
            _mark_failed(db, job, "project no longer exists")
            return

        template = (
            db.query(TemplateProfileRow)
            .filter(TemplateProfileRow.id == project.template_id)
            .one_or_none()
        )
        if template is None:
            _mark_failed(db, job, "template no longer exists")
            return

        # Ensure template.layouts (classifier output) is populated — both
        # so the LLM knows what pages exist and so we can assign default
        # template_slide_index by layout match afterwards. GET
        # /api/templates/{id} does this eagerly but the SQS message
        # might arrive first on a fresh template.
        if not template.layouts or not template.template_slide_count:
            a = analyze_template(template.original_s3_path)
            if a:
                if a.slide_count:
                    template.template_slide_count = a.slide_count
                if a.layouts:
                    template.layouts = a.layouts
                db.commit()

        template_summary = (
            f"テンプレート名: {template.name}\n"
            f"S3: {template.original_s3_path}\n"
            f"総ページ数: {template.template_slide_count}\n"
            f"構成: {_describe_layouts(template.layouts)}"
        )

        try:
            parsed = build_blueprint(
                llm=LLMClient(),
                user_intent=msg["user_intent"],
                required_sections=msg.get("required_sections") or [],
                aux_context=msg.get("aux_context"),
                template_summary=template_summary,
            )
        except BlueprintBuildError as e:
            # Validation/LLM-output failure after retries — don't let SQS
            # redeliver forever, mark failed and ack.
            _mark_failed(db, job, f"blueprint build failed: {e}")
            return

        _assign_template_mapping(parsed.get("slides") or [], template.layouts or [])

        latest = (
            db.query(BlueprintRow)
            .filter(BlueprintRow.project_id == project.id)
            .order_by(BlueprintRow.version.desc())
            .first()
        )
        next_version = (latest.version + 1) if latest else 1

        bp_id = str(uuid4())
        bp = BlueprintRow(
            id=bp_id,
            project_id=project.id,
            version=next_version,
            title=parsed.get("title", project.name),
            slides=parsed.get("slides", []),
        )
        db.add(bp)

        job.status = "complete"
        job.blueprint_id = bp_id
        db.commit()
        log.info("job %s complete -> blueprint %s v%d", job_id, bp_id, next_version)
    except Exception:
        # Transient (DB, Secrets Manager, Anthropic transport). Roll back
        # and re-raise so SQS retries up to the DLQ threshold.
        db.rollback()
        log.exception("blueprint_worker transient failure; will retry")
        raise
    finally:
        db.close()


def _mark_failed(db: Any, job: BlueprintJobRow, error: str) -> None:
    job.status = "failed"
    job.error_message = error[:2000]
    db.commit()
    log.error("job %s failed: %s", job.id, error)


def _describe_layouts(layouts: list[dict]) -> str:
    """Compact human-readable breakdown of a template's pages for the
    blueprint LLM prompt, e.g. '#1 cover, #2 toc, #3-5 content, #6 disclaimer'."""
    if not layouts:
        return "(未分類)"
    return ", ".join(
        f"#{int(layout.get('index', i + 1))} {layout.get('layout', 'content')}"
        for i, layout in enumerate(layouts)
    )


def _assign_template_mapping(
    blueprint_slides: list[dict],
    template_layouts: list[dict],
) -> None:
    """Set template_slide_index on each blueprint slide by matching its
    layout against the classified template pages.

    Strategy:
      - Group template pages by layout type.
      - For a blueprint slide of layout X, cycle through template pages
        of layout X. If no such template page exists, fall back to
        template "content" pages (the generic bucket), then finally to
        a simple positional cycle.

    Mutates blueprint_slides in place. Existing non-null
    template_slide_index values are respected.
    """
    if not template_layouts:
        return  # render handler will do its own positional cycling

    by_type: dict[str, list[int]] = {}
    for entry in template_layouts:
        by_type.setdefault(entry.get("layout", "content"), []).append(
            int(entry.get("index", 0))
        )

    content_pages = by_type.get("content") or []
    total = max((int(entry.get("index", 0)) for entry in template_layouts), default=0)
    if total <= 0:
        return

    counters: dict[str, int] = {}
    for i, slide in enumerate(blueprint_slides):
        if isinstance(slide.get("template_slide_index"), int):
            continue  # user already overrode (won't happen on fresh LLM output, but safe)
        want = slide.get("layout", "content")
        candidates = by_type.get(want) or content_pages
        if not candidates:
            # No content pages either — fall back to positional cycle.
            slide["template_slide_index"] = (i % total) + 1
            continue
        c = counters.get(want, 0)
        slide["template_slide_index"] = candidates[c % len(candidates)]
        counters[want] = c + 1
