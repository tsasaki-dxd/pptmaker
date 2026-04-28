"""
SQS-driven Lambda handler for async revision (per-slide / whole-deck).

Mirrors blueprint_worker.py: each SQS record is one revision job, we
load the RevisionJobRow, call the revision LLM, validate + apply the
JSON Patch, write a new BlueprintRow + RevisionRow, flip job status to
"complete" (or "failed").

Split off the inline POST /revise path because the LLM call routinely
exceeded the API Gateway 29s integration timeout, leaving clients to
see a 503 even when the revision had silently committed in the
background. With a worker the API just enqueues, returns 202, and the
UI polls — no API Gateway timeout in the critical path.

Event source: the RevisionQueue SQS queue (see infra/stacks/app_stack.py).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from uuid import uuid4

from .models.db import (
    BlueprintRow,
    ProjectRow,
    RevisionJobRow,
    RevisionRow,
    new_session,
)
from .services.llm import LLMClient, LLMTruncatedError
from .services.revision_handler import RevisionError, apply_instruction

log = logging.getLogger("slideforge.revision_worker")
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    records = event.get("Records") or []
    if not records:
        log.warning("revision_worker invoked with non-SQS event; ignoring")
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
            db.query(RevisionJobRow)
            .filter(RevisionJobRow.id == job_id)
            .one_or_none()
        )
        if job is None:
            log.error("revision job %s not in DB; dropping", job_id)
            return
        if job.status != "pending":
            # Already processed — SQS at-least-once redelivery.
            log.info(
                "revision job %s already status=%s; skipping", job_id, job.status
            )
            return

        project = (
            db.query(ProjectRow)
            .filter(ProjectRow.id == job.project_id)
            .one_or_none()
        )
        if project is None:
            _mark_failed(db, job, "project no longer exists")
            return

        # Always operate against the LATEST blueprint version. The
        # client doesn't pass an expected version because the inline
        # path used to do the same thing; if the project was edited
        # between job creation and worker pickup, the user intended
        # their instruction to land on whatever is current.
        current = (
            db.query(BlueprintRow)
            .filter(BlueprintRow.project_id == project.id)
            .order_by(BlueprintRow.version.desc())
            .first()
        )
        if current is None:
            _mark_failed(db, job, "no blueprint to revise")
            return

        # Late slide_index validation — it could have gone out of range
        # if some other revision shrunk the deck.
        if job.slide_index is not None and (
            job.slide_index < 1 or job.slide_index > len(current.slides)
        ):
            _mark_failed(
                db,
                job,
                f"slide_index {job.slide_index} out of range "
                f"(1..{len(current.slides)})",
            )
            return

        try:
            patch, new_obj = apply_instruction(
                LLMClient(),
                {"title": current.title, "slides": current.slides},
                job.instruction,
                slide_index=job.slide_index,
            )
        except RevisionError as e:
            _mark_failed(db, job, f"revision rejected: {e}")
            return
        except LLMTruncatedError as e:
            _mark_failed(db, job, f"LLM response truncated: {e}")
            return
        except json.JSONDecodeError as e:
            _mark_failed(db, job, f"LLM returned non-JSON: {e}")
            return
        except ValueError as e:
            # extract_json / jsonpatch internals can raise ValueError
            # on malformed input.
            _mark_failed(db, job, f"revision parse error: {e}")
            return

        new_id = str(uuid4())
        new_bp = BlueprintRow(
            id=new_id,
            project_id=project.id,
            version=current.version + 1,
            title=new_obj.get("title", current.title),
            slides=new_obj.get("slides", current.slides),
        )
        rev = RevisionRow(
            id=str(uuid4()),
            blueprint_id=new_id,
            instruction=job.instruction,
            patch=patch,
            applied=1,
        )
        db.add_all([new_bp, rev])

        job.status = "complete"
        job.blueprint_id = new_id
        db.commit()
        log.info(
            "revision job %s complete -> blueprint %s v%d ops=%d",
            job_id,
            new_id,
            current.version + 1,
            len(patch),
        )
    except Exception:
        # Transient (DB, Secrets Manager, Anthropic transport). Roll
        # back so SQS retries up to the DLQ threshold.
        db.rollback()
        log.exception("revision_worker transient failure; will retry")
        raise
    finally:
        db.close()


def _mark_failed(db: Any, job: RevisionJobRow, error: str) -> None:
    job.status = "failed"
    job.error_message = error[:2000]
    db.commit()
    log.error("revision job %s failed: %s", job.id, error)
