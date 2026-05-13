"""External integration API (async polling design).

For service-to-service callers (report_bot on Cloud Run that posts the
rendered deck back to Google Chat). The user-facing flow is multi-step
on purpose (draft → blueprint → tweak → render → export); this collapses
it into a single submit + poll pair:

  POST /api/v1/external/slides       → 202 queued
  GET  /api/v1/external/slides/{id}  → queued / rendering / done / error

The synchronous wait=True path used to live here but blueprint LLM call
+ render (~30-90s combined) overruns API Gateway HTTP API's 30s
integration timeout, so the request returned 503 even when the job
eventually succeeded. The polling design moves all the work onto the
SQS-driven blueprint + render workers.

Auth: a Cognito access token issued via client_credentials grant with
scope `slideforge-api/slides:create`. See README → "外部サービスからの
呼び出し方".
"""

from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import current_user_id, require_scope, require_tenant
from ..config import get_settings
from ..models.db import (
    BlueprintJobRow,
    BlueprintRow,
    ProjectRow,
    TemplateProfileRow,
    get_session,
)
from ..services.queue import BlueprintQueue
from ..services.storage import Storage

log = logging.getLogger("slideforge.external")

_require_external_scope = require_scope(
    get_settings().external_api_required_scope
)

router = APIRouter(prefix="/api/v1/external", tags=["external"])


# Stable response schema for both POST and GET. report_bot keys off the
# field names directly, so additions are fine but renames / removals
# are breaking changes — bump /api/v2/ when that day comes.
ExternalStatus = Literal["queued", "blueprint", "rendering", "done", "error"]


class ExternalSlideRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    # Accepts the template UUID or its display name (exact match, then
    # case-insensitive fallback, newest-wins on duplicates). report_bot
    # ships with the production template name so it stays agnostic of
    # the underlying UUID across re-uploads.
    template_id: str = Field(default="DXDesignSystem", min_length=1)
    report_markdown: str = Field(min_length=1)
    source_url: str | None = None


class ExternalSlideResponse(BaseModel):
    project_id: str
    status: ExternalStatus
    pptx_url: str | None = None
    pdf_url: str | None = None
    preview_urls: list[str] | None = None
    error: str | None = None


@router.post("/slides", response_model=ExternalSlideResponse, status_code=202)
def create_slides(
    body: ExternalSlideRequest,
    tenant_id: str = Depends(require_tenant),
    user_id: str = Depends(current_user_id),
    _scope: dict = Depends(_require_external_scope),
    db: Session = Depends(get_session),
    # Idempotency-Key is forwarded by report_bot on retry; accepted-
    # but-ignored in Phase 1. A new table is needed for real dedupe and
    # we don't want to add one yet — the header is wired here so the
    # caller can adopt it now and we just turn dedupe on without an API
    # change later.
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ExternalSlideResponse:
    """Submit a markdown report for rendering. Returns immediately.

    Always 202; failures map to 200 + status="error" in the GET (never
    5xx for application errors) so the caller's polling logic doesn't
    need separate transport-error branches.
    """
    template = _resolve_template(db, body.template_id, tenant_id)
    if template is None:
        # Lookup failure surfaces synchronously — the alternative is
        # writing a "failed" job to the DB just so the GET can report
        # it, which adds noise. report_bot can branch on
        # status="error" returned right here, same as any other error
        # path, so the contract stays uniform.
        log.warning(
            "external slides: template %r not found (tenant=%s)",
            body.template_id, tenant_id,
        )
        # project_id of all-zeros is a recognizable sentinel so the
        # caller can tell "we never created anything" apart from
        # "created but error mid-flight".
        return ExternalSlideResponse(
            project_id=str(UUID(int=0)),
            status="error",
            error=f"template not found: {body.template_id!r}",
        )

    project = ProjectRow(
        id=str(uuid4()),
        tenant_id=tenant_id,
        owner_user_id=user_id,
        name=body.title,
        template_id=template.id,
        status="draft",
    )
    db.add(project)
    db.flush()  # allocate id before referencing it from the job row

    job = BlueprintJobRow(
        id=str(uuid4()),
        project_id=project.id,
        tenant_id=tenant_id,
        status="pending",
    )
    db.add(job)
    db.commit()

    BlueprintQueue().submit(
        {
            "job_id": job.id,
            "project_id": project.id,
            "tenant_id": tenant_id,
            "user_intent": _compose_intent(body),
            "required_sections": [],
            "aux_context": body.source_url,
            # Tells blueprint_worker to chain a render job onto SQS as
            # soon as the blueprint commits. Web UI jobs don't set this
            # — the user clicks "render" themselves after reviewing.
            "auto_render": True,
        }
    )
    log.info(
        "external slides queued project=%s job=%s caller=%s idem=%s",
        project.id, job.id, user_id, idempotency_key,
    )

    return ExternalSlideResponse(
        project_id=project.id,
        status="queued",
    )


@router.get("/slides/{project_id}", response_model=ExternalSlideResponse)
def get_slides_status(
    project_id: str,
    tenant_id: str = Depends(require_tenant),
    _user_id: str = Depends(current_user_id),
    _scope: dict = Depends(_require_external_scope),
    db: Session = Depends(get_session),
) -> ExternalSlideResponse:
    """Poll for completion. Always 200; the `status` field carries the state.

    The error path returns the same 200 shape so report_bot can branch
    on a single field instead of mixing HTTP status code handling with
    response parsing.
    """
    project = (
        db.query(ProjectRow)
        .filter(
            ProjectRow.id == project_id,
            ProjectRow.tenant_id == tenant_id,
        )
        .one_or_none()
    )
    if project is None:
        return ExternalSlideResponse(
            project_id=project_id,
            status="error",
            error="project not found",
        )

    # Latest blueprint job for the project. There's only ever one for
    # the external API (POST creates one and we never re-fire), but
    # order-by-created keeps things sane if someone wires up a retry
    # path later.
    job = (
        db.query(BlueprintJobRow)
        .filter(BlueprintJobRow.project_id == project_id)
        .order_by(BlueprintJobRow.created_at.desc())
        .first()
    )

    status, error = _derive_status(project, job)
    response = ExternalSlideResponse(
        project_id=project.id,
        status=status,
        error=error,
    )
    if status == "done":
        _attach_download_urls(response, db, project)
    return response


# -------- helpers --------


def _derive_status(
    project: ProjectRow, job: BlueprintJobRow | None
) -> tuple[ExternalStatus, str | None]:
    """Collapse (BlueprintJob.status, project.status) into a single state.

    The two underlying rows are updated by different actors (blueprint
    worker writes the job + flips project to "rendering"; render Lambda
    writes the final project status), so the polling client wants one
    canonical answer instead of having to reason about both.
    """
    # Blueprint hard-failed → terminal error. project.status will still
    # be "draft" at this point because the render Lambda never ran.
    if job is not None and job.status == "failed":
        return "error", job.error_message or "blueprint failed"

    # Render Lambda flips project.status to "failed" on its own
    # terminal errors (e.g. LibreOffice crash). Treated identically to
    # blueprint failure from the caller's perspective.
    if project.status == "failed":
        return "error", "render failed"

    if project.status in ("complete", "partial"):
        # "partial" means some slides rendered and some didn't. The
        # caller still gets URLs (the rendered slides land in S3); the
        # error field stays null because the deck is usable.
        return "done", None

    # Pre-render phase: blueprint job is the source of truth.
    if job is None or job.status == "pending":
        return "queued", None

    # Blueprint complete, render in flight. project.status flips to
    # "rendering" inside blueprint_worker._submit_render right after
    # the SQS enqueue.
    return "rendering", None


def _attach_download_urls(
    response: ExternalSlideResponse,
    db: Session,
    project: ProjectRow,
) -> None:
    """Populate pptx / pdf / preview URLs on a done response.

    Generated per-request (not cached) so each poll returns fresh 24h
    presigned URLs — important because report_bot can re-poll long
    after the deck completed, e.g. if Google Chat retries on its end.
    """
    bp = (
        db.query(BlueprintRow)
        .filter(BlueprintRow.project_id == project.id)
        .order_by(BlueprintRow.version.desc())
        .first()
    )
    if bp is None:
        # project.status="complete" without a BlueprintRow is a
        # state-machine bug. Don't crash — just leave URLs null and let
        # the operator see the inconsistency via CloudWatch.
        log.error("project %s status=done but no blueprint row", project.id)
        return

    storage = Storage()
    prefix = storage.output_prefix(project.tenant_id, project.id, bp.version)
    # 24h presigned URLs so retries on the Google Chat side have plenty
    # of time to download. SigV4 caps at 7 days but 24h is a sane
    # middle ground — short enough that a leaked URL doesn't stay live
    # forever, long enough for any reasonable retry budget.
    expires = 24 * 3600
    response.pptx_url = storage.presign_download(prefix + "output.pptx", expires=expires)
    response.pdf_url = storage.presign_download(prefix + "output.pdf", expires=expires)
    response.preview_urls = [
        storage.presign_download(
            f"{prefix}preview/slide-{i:02d}.jpg", expires=expires
        )
        for i in range(1, len(bp.slides) + 1)
    ]


def _resolve_template(
    db: Session, raw: str, tenant_id: str
) -> TemplateProfileRow | None:
    """Treat ``raw`` as a UUID first, then as a name within the tenant.

    Accepting both lets the caller stay agnostic of the template id:
    report_bot ships with ``template_id="DXDesignSystem"`` which
    resolves by name. If the same name maps to multiple rows (rename
    + re-upload), pick the newest — almost always what the caller
    meant.
    """
    try:
        UUID(raw)
        row = (
            db.query(TemplateProfileRow)
            .filter(
                TemplateProfileRow.id == raw,
                TemplateProfileRow.tenant_id == tenant_id,
            )
            .one_or_none()
        )
        if row is not None:
            return row
    except ValueError:
        pass

    row = (
        db.query(TemplateProfileRow)
        .filter(
            TemplateProfileRow.tenant_id == tenant_id,
            TemplateProfileRow.name == raw,
        )
        .order_by(TemplateProfileRow.created_at.desc())
        .first()
    )
    if row is not None:
        return row
    return (
        db.query(TemplateProfileRow)
        .filter(TemplateProfileRow.tenant_id == tenant_id)
        .filter(TemplateProfileRow.name.ilike(raw))
        .order_by(TemplateProfileRow.created_at.desc())
        .first()
    )


def _compose_intent(body: ExternalSlideRequest) -> str:
    """Build the LLM user_intent prompt from the request body.

    Blueprint builder expects a single freeform string. We bundle
    title + markdown so the LLM sees both the deck's stated purpose
    and the source material. source_url is forwarded as aux_context
    by the caller (kept separate so the LLM can cite it rather than
    treat it as content).
    """
    return (
        "以下のレポートをスライドに変換してください。\n\n"
        f"タイトル: {body.title}\n\n"
        f"レポート本文:\n{body.report_markdown}"
    )
