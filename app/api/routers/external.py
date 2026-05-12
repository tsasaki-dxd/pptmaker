"""External integration API.

Single-shot "markdown report in, slide URLs out" endpoint for service-to-
service callers (e.g. report_bot on Cloud Run that posts the rendered
deck back to Google Chat). The user-facing flow is multi-step on purpose
(draft → blueprint → tweak → render → export); this collapses it into
one call:

  1. Resolve or look up the template
  2. Create a project owned by the calling client
  3. Generate the blueprint inline (no SQS hop — we're going to wait
     anyway, and the LLM call fits inside the worker's 5-minute budget)
  4. Submit render to the existing SQS queue
  5. Poll ProjectRow.status until "complete" / "partial" / "failed"
  6. Return presigned S3 URLs to the .pptx / .pdf / preview PNGs

Auth: requires a Cognito access token issued via the client_credentials
grant with scope `slideforge-api/slides:create`. See README →
"外部サービスからの呼び出し方".
"""

from __future__ import annotations

import logging
import time
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import current_user_id, require_scope, require_tenant
from ..config import get_settings
from ..models.db import (
    BlueprintRow,
    ProjectRow,
    TemplateProfileRow,
    get_session,
    new_session,
)
from ..services.blueprint_builder import BlueprintBuildError, build_blueprint
from ..services.llm import LLMClient
from ..services.queue import RenderQueue
from ..services.storage import Storage
from ..services.template_analyzer import analyze_template

log = logging.getLogger("slideforge.external")

# Re-uses the API's existing scope-check dependency. The required scope
# string is taken from settings so a local-dev / pytest run with no
# EXTERNAL_API_REQUIRED_SCOPE env var falls back to the production value.
_require_external_scope = require_scope(
    get_settings().external_api_required_scope
)

router = APIRouter(prefix="/api/v1/external", tags=["external"])


class ExternalSlideRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    # Accepts either the template UUID or its display name (case-sensitive
    # exact match within the calling tenant). The default lets the
    # report_bot caller stay agnostic of the UUID — operations replace
    # the template under the same name without code changes.
    template_id: str = Field(default="DXDesignSystem", min_length=1)
    report_markdown: str = Field(min_length=1)
    source_url: str | None = None
    wait: bool = True
    # Hard ceiling — render rarely exceeds 90s even for 20-slide decks,
    # so 180s leaves headroom for blueprint + render combined. The
    # caller can crank this to ~300s for unusually large reports; above
    # that, switch to wait=False and poll separately.
    timeout_sec: int = Field(default=180, ge=10, le=600)


class ExternalSlideResponse(BaseModel):
    project_id: UUID
    status: Literal["done", "pending", "error"]
    pptx_url: str | None = None
    pdf_url: str | None = None
    preview_urls: list[str] | None = None
    error: str | None = None


@router.post("/slides", response_model=ExternalSlideResponse)
def create_slides(
    body: ExternalSlideRequest,
    tenant_id: str = Depends(require_tenant),
    user_id: str = Depends(current_user_id),
    _scope: dict = Depends(_require_external_scope),
    db: Session = Depends(get_session),
    # Idempotency-Key is forwarded by report_bot when retrying after a
    # transport hiccup. We don't dedupe in Phase 1 (would need a new
    # table); the header is accepted-but-ignored so callers can wire it
    # in now and we just turn it on later without an API break.
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ExternalSlideResponse:
    template = _resolve_template(db, body.template_id, tenant_id)
    if template is None:
        return ExternalSlideResponse(
            project_id=UUID(int=0),
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
    db.commit()
    db.refresh(project)
    log.info(
        "external project created project=%s tenant=%s caller=%s idem=%s",
        project.id, tenant_id, user_id, idempotency_key,
    )

    try:
        bp_row = _generate_blueprint_inline(
            db=db,
            project=project,
            template=template,
            user_intent=_compose_intent(body),
            aux_context=body.source_url,
        )
    except BlueprintBuildError as e:
        return ExternalSlideResponse(
            project_id=UUID(project.id),
            status="error",
            error=f"blueprint failed: {e}",
        )

    if not body.wait:
        return ExternalSlideResponse(
            project_id=UUID(project.id),
            status="pending",
        )

    storage = Storage()
    _submit_render(storage, tenant_id, project, template, bp_row)

    final_status = _wait_for_render(project.id, body.timeout_sec)
    if final_status in ("complete", "partial"):
        return _build_done_response(storage, tenant_id, project.id, bp_row)
    if final_status == "failed":
        return ExternalSlideResponse(
            project_id=UUID(project.id),
            status="error",
            error="render failed (see CloudWatch for render Lambda errors)",
        )
    # Timed out — caller can poll /api/projects/{id} or re-issue with a
    # larger timeout_sec.
    return ExternalSlideResponse(
        project_id=UUID(project.id),
        status="pending",
        error=f"render did not finish within {body.timeout_sec}s",
    )


def _resolve_template(
    db: Session, raw: str, tenant_id: str
) -> TemplateProfileRow | None:
    """Treat ``raw`` as a UUID first, then as a name within the tenant.

    Accepting both lets the external caller stay agnostic of the
    template id: report_bot ships with ``template_id="DXDesignSystem"``,
    which resolves by name as long as the template exists in the
    tenant's catalog under that exact name.
    """
    # UUID path
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

    # Name path — exact match wins, then a case-insensitive fallback so
    # a caller passing "dxdesignsystem" still resolves. If a name was
    # uploaded twice (rename + re-upload pattern), pick the most
    # recent — it's almost always what the caller meant.
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
    """Build the LLM user_intent prompt from the request.

    Blueprint builder expects a single freeform string. We concatenate
    title + markdown so the LLM sees both the deck's stated purpose and
    the underlying source material. The source_url, when present, is
    forwarded as aux_context (kept separate so the LLM can cite it
    rather than treat it as content).
    """
    return (
        f"以下のレポートをスライドに変換してください。\n\n"
        f"タイトル: {body.title}\n\n"
        f"レポート本文:\n{body.report_markdown}"
    )


def _generate_blueprint_inline(
    *,
    db: Session,
    project: ProjectRow,
    template: TemplateProfileRow,
    user_intent: str,
    aux_context: str | None,
) -> BlueprintRow:
    """Run the blueprint LLM call on the request thread and persist the result.

    Mirrors blueprint_worker._process but without the SQS / job-row
    overhead — there's nothing to poll because we're going to wait
    anyway. The render path downstream still goes through SQS.
    """
    # Lazy-analyze the template if it was uploaded but never inspected
    # (would normally happen on first GET /api/templates/{id}).
    if not template.layouts or not template.template_slide_count:
        analysis = analyze_template(template.original_s3_path)
        if analysis:
            if analysis.slide_count:
                template.template_slide_count = analysis.slide_count
            if analysis.layouts:
                template.layouts = analysis.layouts
            if analysis.design_tokens:
                merged = dict(template.design_tokens or {})
                merged.update(analysis.design_tokens)
                template.design_tokens = merged
            db.commit()

    template_summary = (
        f"テンプレート名: {template.name}\n"
        f"S3: {template.original_s3_path}\n"
        f"総ページ数: {template.template_slide_count}\n"
        f"構成: {_describe_layouts(template.layouts)}"
    )

    parsed = build_blueprint(
        llm=LLMClient(),
        user_intent=user_intent,
        required_sections=[],
        aux_context=aux_context,
        template_summary=template_summary,
    )

    # Same template-slide-index assignment as the async worker. Kept
    # local rather than imported because it's an implementation detail
    # of how blueprints get rendered, not a public service.
    _assign_template_mapping(parsed.get("slides") or [], template.layouts or [])

    bp_row = BlueprintRow(
        id=str(uuid4()),
        project_id=project.id,
        version=1,
        title=parsed.get("title", project.name),
        slides=parsed.get("slides", []),
    )
    db.add(bp_row)
    db.commit()
    db.refresh(bp_row)
    log.info(
        "external blueprint generated project=%s blueprint=%s slides=%d",
        project.id, bp_row.id, len(bp_row.slides),
    )
    return bp_row


def _submit_render(
    storage: Storage,
    tenant_id: str,
    project: ProjectRow,
    template: TemplateProfileRow,
    bp: BlueprintRow,
) -> None:
    """Submit the render job to SQS and flip project.status to "rendering"."""
    out_prefix = storage.output_prefix(tenant_id, project.id, bp.version)
    RenderQueue().submit(
        {
            "job_id": str(uuid4()),
            "tenant_id": tenant_id,
            "project_id": project.id,
            "template_s3": template.original_s3_path,
            "blueprint": {"title": bp.title, "slides": bp.slides},
            "template_layouts": list(template.layouts or []),
            "design_tokens": dict(template.design_tokens or {}),
            "out_prefix": storage.as_uri(out_prefix),
        }
    )
    # Best-effort status flip so the projects list shows the external
    # job as in-flight. The render Lambda's db_status writer will move
    # it to "complete" / "partial" / "failed".
    project.status = "rendering"


def _wait_for_render(project_id: str, timeout_sec: int) -> str | None:
    """Poll ProjectRow.status until the render Lambda flips it.

    Uses a fresh session per poll so the SQLAlchemy session doesn't
    keep the row cached at the original "rendering" value (the render
    Lambda commits via a separate connection). Returns the final status
    string, or None if the timeout elapses while it's still
    "rendering".
    """
    terminal = {"complete", "partial", "failed"}
    deadline = time.monotonic() + timeout_sec
    # Start with short pings and back off — most renders finish in 30-90s.
    delay = 2.0
    while time.monotonic() < deadline:
        time.sleep(delay)
        db = new_session()
        try:
            row = (
                db.query(ProjectRow).filter(ProjectRow.id == project_id).one_or_none()
            )
            if row is None:
                return "failed"
            if row.status in terminal:
                return row.status
        finally:
            db.close()
        # Cap at 5s — render finishes within a single API Gateway
        # request budget regardless of poll cadence; keep it responsive.
        delay = min(delay * 1.5, 5.0)
    return None


def _build_done_response(
    storage: Storage, tenant_id: str, project_id: str, bp: BlueprintRow
) -> ExternalSlideResponse:
    prefix = storage.output_prefix(tenant_id, project_id, bp.version)
    # 24h presigned URLs so the consumer (Google Chat webhook + any
    # downstream retries) has plenty of time to download or relay them.
    pptx_url = storage.presign_download(prefix + "output.pptx", expires=24 * 3600)
    pdf_url = storage.presign_download(prefix + "output.pdf", expires=24 * 3600)
    previews = [
        storage.presign_download(
            f"{prefix}preview/slide-{i:02d}.jpg", expires=24 * 3600
        )
        for i in range(1, len(bp.slides) + 1)
    ]
    return ExternalSlideResponse(
        project_id=UUID(project_id),
        status="done",
        pptx_url=pptx_url,
        pdf_url=pdf_url,
        preview_urls=previews,
    )


def _describe_layouts(layouts: list[dict]) -> str:
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
    """Same algorithm as blueprint_worker — kept duplicated rather than
    imported so the worker and external paths don't grow a shared
    helpers module just for this. If a third caller appears, lift it
    out then."""
    if not template_layouts:
        return
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
            continue
        want = slide.get("layout", "content")
        candidates = by_type.get(want) or content_pages
        if not candidates:
            slide["template_slide_index"] = (i % total) + 1
            continue
        c = counters.get(want, 0)
        slide["template_slide_index"] = candidates[c % len(candidates)]
        counters[want] = c + 1
