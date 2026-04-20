"""Project CRUD + blueprint + revision + render endpoints."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_tenant
from ..models.db import BlueprintRow, ProjectRow, RevisionRow, TemplateProfileRow, get_session
from ..models.schemas import (
    Blueprint,
    BlueprintCreate,
    Project,
    ProjectCreate,
    RenderResponse,
    Revision,
    RevisionCreate,
    SlideSpec,
)
from ..services.blueprint_builder import BlueprintBuildError, build_blueprint
from ..services.llm import LLMClient
from ..services.queue import RenderQueue
from ..services.revision_handler import RevisionError, apply_instruction
from ..services.storage import Storage

log = logging.getLogger("slideforge.projects")

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Figure-type catalog sent to the blueprint LLM. Kept terse.
FIGURE_CATALOG = (
    "- table: 行×列の表、ヘッダ+交互背景。content: {title?, headers, rows}\n"
    "- cards_grid: 均等カード格子。content: {cards:[{title, body}], columns?}\n"
    "- two_column: 左右2カラム+任意フッタ。content: {left, right, footer?}\n"
    "- timeline: 横タイムライン。content: {steps:[{label, body?}]}\n"
    "- stat_callout: 数値強調。content: {value, label, note?}\n"
    "- bullet_list: 箇条書き。content: {items:[...]}\n"
    "- comparison: 左右比較。content: {left:{title, items}, right:{title, items}}\n"
)


@router.post("", response_model=Project)
def create_project(
    body: ProjectCreate,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> Project:
    row = ProjectRow(
        id=str(uuid4()),
        tenant_id=tenant_id,
        name=body.name,
        template_id=str(body.template_id),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return Project(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        template_id=row.template_id,
        status=row.status,
        created_at=row.created_at,
    )


@router.post("/{project_id}/blueprint", response_model=Blueprint)
def create_blueprint(
    project_id: str,
    body: BlueprintCreate,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> Blueprint:
    project = _load_project(db, project_id, tenant_id)
    template = (
        db.query(TemplateProfileRow)
        .filter(TemplateProfileRow.id == project.template_id)
        .one()
    )

    template_summary = (
        f"テンプレート名: {template.name}\n"
        f"S3: {template.original_s3_path}\n"
        f"レイアウト数: {len(template.layouts)}"
    )

    llm = LLMClient()
    try:
        parsed = build_blueprint(
            llm=llm,
            user_intent=body.intent,
            required_sections=body.required_sections,
            aux_context=body.aux_context,
            template_summary=template_summary,
            figure_catalog=FIGURE_CATALOG,
        )
    except BlueprintBuildError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    row = BlueprintRow(
        id=str(uuid4()),
        project_id=project.id,
        version=_next_version(db, project.id),
        title=parsed.get("title", project.name),
        slides=parsed.get("slides", []),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return _to_schema(row)


@router.get("/{project_id}/blueprint", response_model=Blueprint)
def get_latest_blueprint(
    project_id: str,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> Blueprint:
    project = _load_project(db, project_id, tenant_id)
    row = (
        db.query(BlueprintRow)
        .filter(BlueprintRow.project_id == project.id)
        .order_by(BlueprintRow.version.desc())
        .first()
    )
    if not row:
        raise HTTPException(404, "no blueprint yet")
    return _to_schema(row)


@router.post("/{project_id}/revise", response_model=Revision)
def revise(
    project_id: str,
    body: RevisionCreate,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> Revision:
    project = _load_project(db, project_id, tenant_id)
    current = (
        db.query(BlueprintRow)
        .filter(BlueprintRow.project_id == project.id)
        .order_by(BlueprintRow.version.desc())
        .first()
    )
    if not current:
        raise HTTPException(400, "no existing blueprint")

    llm = LLMClient()
    try:
        patch, new_slides_obj = apply_instruction(
            llm,
            {"title": current.title, "slides": current.slides},
            body.instruction,
        )
    except RevisionError as e:
        raise HTTPException(400, str(e)) from e

    new_row = BlueprintRow(
        id=str(uuid4()),
        project_id=project.id,
        version=current.version + 1,
        title=new_slides_obj.get("title", current.title),
        slides=new_slides_obj.get("slides", current.slides),
    )
    rev = RevisionRow(
        id=str(uuid4()),
        blueprint_id=new_row.id,
        instruction=body.instruction,
        patch=patch,
        applied=1,
    )
    db.add_all([new_row, rev])
    db.commit()
    db.refresh(rev)

    return Revision(
        id=rev.id,
        blueprint_id=rev.blueprint_id,
        instruction=rev.instruction,
        patch=rev.patch,
        applied=bool(rev.applied),
        created_at=rev.created_at,
    )


@router.post("/{project_id}/render", response_model=RenderResponse)
def render(
    project_id: str,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> RenderResponse:
    project = _load_project(db, project_id, tenant_id)
    bp = (
        db.query(BlueprintRow)
        .filter(BlueprintRow.project_id == project.id)
        .order_by(BlueprintRow.version.desc())
        .first()
    )
    if not bp:
        raise HTTPException(400, "no blueprint")

    template = (
        db.query(TemplateProfileRow)
        .filter(TemplateProfileRow.id == project.template_id)
        .one()
    )

    storage = Storage()
    out_prefix = storage.output_prefix(tenant_id, project.id, bp.version)

    job = {
        "job_id": str(uuid4()),
        "tenant_id": tenant_id,
        "project_id": project.id,
        "template_s3": template.original_s3_path,
        "blueprint": {"title": bp.title, "slides": bp.slides},
        "out_prefix": storage.as_uri(out_prefix),
    }
    RenderQueue().submit(job)
    log.info("render job submitted project=%s blueprint=%s", project.id, bp.id)

    return RenderResponse(job_id=job["job_id"], blueprint_id=bp.id, status="queued")


@router.get("/{project_id}/preview/{slide_index}")
def preview(
    project_id: str,
    slide_index: int,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> dict:
    project = _load_project(db, project_id, tenant_id)
    bp = (
        db.query(BlueprintRow)
        .filter(BlueprintRow.project_id == project.id)
        .order_by(BlueprintRow.version.desc())
        .first()
    )
    if not bp:
        raise HTTPException(404, "no blueprint")
    storage = Storage()
    key = storage.output_prefix(tenant_id, project.id, bp.version) + f"preview/slide-{slide_index:02d}.jpg"
    return {"slide_index": slide_index, "url": storage.presign_download(key)}


@router.get("/{project_id}/export")
def export(
    project_id: str,
    tenant_id: str = Depends(require_tenant),
    format: str = "pptx",
    db: Session = Depends(get_session),
) -> dict:
    if format not in ("pptx", "pdf"):
        raise HTTPException(400, "format must be pptx or pdf")
    project = _load_project(db, project_id, tenant_id)
    bp = (
        db.query(BlueprintRow)
        .filter(BlueprintRow.project_id == project.id)
        .order_by(BlueprintRow.version.desc())
        .first()
    )
    if not bp:
        raise HTTPException(404, "no blueprint")
    storage = Storage()
    name = "output.pptx" if format == "pptx" else "output.pdf"
    key = storage.output_prefix(tenant_id, project.id, bp.version) + name
    return {"format": format, "url": storage.presign_download(key)}


def _load_project(db: Session, project_id: str, tenant_id: str) -> ProjectRow:
    row = (
        db.query(ProjectRow)
        .filter(ProjectRow.id == project_id, ProjectRow.tenant_id == tenant_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "project not found")
    return row


def _next_version(db: Session, project_id: str) -> int:
    latest = (
        db.query(BlueprintRow)
        .filter(BlueprintRow.project_id == project_id)
        .order_by(BlueprintRow.version.desc())
        .first()
    )
    return (latest.version + 1) if latest else 1


def _to_schema(row: BlueprintRow) -> Blueprint:
    return Blueprint(
        id=row.id,
        project_id=row.project_id,
        version=row.version,
        title=row.title,
        slides=[SlideSpec(**s) for s in row.slides],
        created_at=row.created_at,
    )
