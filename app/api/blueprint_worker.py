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
from .services.blueprint_builder import (
    FIGURE_CATALOG,
    BlueprintBuildError,
    build_blueprint,
)
from .services.llm import LLMClient

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

        template_summary = (
            f"テンプレート名: {template.name}\n"
            f"S3: {template.original_s3_path}\n"
            f"レイアウト数: {len(template.layouts)}"
        )

        try:
            parsed = build_blueprint(
                llm=LLMClient(),
                user_intent=msg["user_intent"],
                required_sections=msg.get("required_sections") or [],
                aux_context=msg.get("aux_context"),
                template_summary=template_summary,
                figure_catalog=FIGURE_CATALOG,
            )
        except BlueprintBuildError as e:
            # Validation/LLM-output failure after retries — don't let SQS
            # redeliver forever, mark failed and ack.
            _mark_failed(db, job, f"blueprint build failed: {e}")
            return

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
