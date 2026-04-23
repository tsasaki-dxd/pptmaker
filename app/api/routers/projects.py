"""Project CRUD + blueprint + revision + render endpoints."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_tenant
from ..models.db import (
    BlueprintJobRow,
    BlueprintRow,
    OutputRow,
    ProjectRow,
    RevisionRow,
    TemplateProfileRow,
    get_session,
)
from ..models.schemas import (
    Blueprint,
    BlueprintCreate,
    BlueprintJob,
    Project,
    ProjectCreate,
    RenderResponse,
    Revision,
    RevisionCreate,
    SlideMappingPatch,
    SlideSpec,
)
from ..services.llm import LLMClient
from ..services.queue import BlueprintQueue, RenderQueue
from ..services.revision_handler import RevisionError, apply_instruction
from ..services.storage import Storage

log = logging.getLogger("slideforge.projects")

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[Project])
def list_projects(
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> list[Project]:
    rows = (
        db.query(ProjectRow)
        .filter(ProjectRow.tenant_id == tenant_id)
        .order_by(ProjectRow.created_at.desc())
        .all()
    )
    return [
        Project(
            id=r.id,
            tenant_id=r.tenant_id,
            name=r.name,
            template_id=r.template_id,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/{project_id}", response_model=Project)
def get_project(
    project_id: str,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> Project:
    row = _load_project(db, project_id, tenant_id)
    return Project(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        template_id=row.template_id,
        status=row.status,
        created_at=row.created_at,
    )


@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> dict:
    """Cascade-delete the project's blueprints, revisions, jobs,
    output rows, and the entire S3 prefix for the project."""
    row = _load_project(db, project_id, tenant_id)

    # Collect blueprint ids before deleting so we can clean up child
    # rows by id (no FK ON DELETE CASCADE in the schema).
    bp_ids = [
        bp_id
        for (bp_id,) in db.query(BlueprintRow.id)
        .filter(BlueprintRow.project_id == project_id)
        .all()
    ]
    if bp_ids:
        db.query(RevisionRow).filter(RevisionRow.blueprint_id.in_(bp_ids)).delete(
            synchronize_session=False
        )
        db.query(OutputRow).filter(OutputRow.blueprint_id.in_(bp_ids)).delete(
            synchronize_session=False
        )
    db.query(BlueprintJobRow).filter(BlueprintJobRow.project_id == project_id).delete(
        synchronize_session=False
    )
    db.query(BlueprintRow).filter(BlueprintRow.project_id == project_id).delete(
        synchronize_session=False
    )

    storage = Storage()
    deleted_objects = storage.delete_prefix(storage.project_prefix(tenant_id, project_id))

    db.delete(row)
    db.commit()
    log.info("project %s deleted (s3 objects removed=%d)", project_id, deleted_objects)
    return {"deleted": project_id, "s3_objects_deleted": deleted_objects}


@router.post("/{project_id}/duplicate", response_model=Project)
def duplicate_project(
    project_id: str,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> Project:
    """Copy a project and its latest blueprint into a new project that
    starts at status="draft". Outputs are intentionally not copied —
    the user is going to edit the blueprint in step 2 anyway, so a
    fresh render is the right state to land in.
    """
    src = _load_project(db, project_id, tenant_id)
    new_project = ProjectRow(
        id=str(uuid4()),
        tenant_id=tenant_id,
        name=f"{src.name} (copy)",
        template_id=src.template_id,
        status="draft",
    )
    db.add(new_project)
    db.flush()  # allocate id before referencing it from the blueprint copy

    latest_bp = (
        db.query(BlueprintRow)
        .filter(BlueprintRow.project_id == src.id)
        .order_by(BlueprintRow.version.desc())
        .first()
    )
    if latest_bp:
        db.add(
            BlueprintRow(
                id=str(uuid4()),
                project_id=new_project.id,
                version=1,
                title=latest_bp.title,
                # JSON column — pass through directly. Slides keep their
                # template_slide_index assignments.
                slides=list(latest_bp.slides),
            )
        )

    db.commit()
    db.refresh(new_project)
    return Project(
        id=new_project.id,
        tenant_id=new_project.tenant_id,
        name=new_project.name,
        template_id=new_project.template_id,
        status=new_project.status,
        created_at=new_project.created_at,
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


@router.post(
    "/{project_id}/blueprint",
    response_model=BlueprintJob,
    status_code=202,
)
def create_blueprint(
    project_id: str,
    body: BlueprintCreate,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> BlueprintJob:
    """Enqueue a blueprint-generation job.

    The LLM call takes ~30s which sits right at the HTTP API v2
    integration timeout of 30s. Doing it inline would turn into a 503.
    Instead, persist a BlueprintJobRow, send an SQS message for the
    blueprint_worker Lambda, and return 202. The client polls
    GET /blueprint/job/{job_id}.
    """
    project = _load_project(db, project_id, tenant_id)
    # Surface "template deleted" up front instead of letting the worker
    # find out 10 seconds in.
    db.query(TemplateProfileRow).filter(
        TemplateProfileRow.id == project.template_id
    ).one()

    job = BlueprintJobRow(
        id=str(uuid4()),
        project_id=project.id,
        tenant_id=tenant_id,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    BlueprintQueue().submit(
        {
            "job_id": job.id,
            "project_id": project.id,
            "tenant_id": tenant_id,
            "user_intent": body.intent,
            "required_sections": list(body.required_sections),
            "aux_context": body.aux_context,
        }
    )

    return BlueprintJob(
        job_id=job.id,
        project_id=job.project_id,
        status=job.status,  # "pending"
        created_at=job.created_at,
    )


@router.get("/{project_id}/blueprint/job/{job_id}", response_model=BlueprintJob)
def get_blueprint_job(
    project_id: str,
    job_id: str,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> BlueprintJob:
    row = (
        db.query(BlueprintJobRow)
        .filter(
            BlueprintJobRow.id == job_id,
            BlueprintJobRow.project_id == project_id,
            BlueprintJobRow.tenant_id == tenant_id,
        )
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "job not found")
    return BlueprintJob(
        job_id=row.id,
        project_id=row.project_id,
        status=row.status,  # type: ignore[arg-type]
        blueprint_id=row.blueprint_id,
        error=row.error_message,
        created_at=row.created_at,
    )


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


@router.patch("/{project_id}/blueprint", response_model=Blueprint)
def patch_blueprint_slide_mapping(
    project_id: str,
    body: SlideMappingPatch,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> Blueprint:
    """Update template_slide_index on individual blueprint slides.

    Body: {"mappings": [{"index": 1, "template_slide_index": 2}, ...]}
    Indices not present in the payload are left untouched. Updates the
    LATEST blueprint version in place — does not create a new revision.
    """
    project = _load_project(db, project_id, tenant_id)
    row = (
        db.query(BlueprintRow)
        .filter(BlueprintRow.project_id == project.id)
        .order_by(BlueprintRow.version.desc())
        .first()
    )
    if not row:
        raise HTTPException(404, "no blueprint yet")

    by_index = {m.index: m.template_slide_index for m in body.mappings}
    # row.slides is a JSON column — mutate a copy and reassign so
    # SQLAlchemy notices the change.
    new_slides = []
    for s in row.slides:
        s = dict(s)
        if s.get("index") in by_index:
            s["template_slide_index"] = by_index[s["index"]]
        new_slides.append(s)
    row.slides = new_slides
    db.commit()
    db.refresh(row)
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

    # Flip the project out of "draft" so the UI can distinguish projects
    # whose render has at least been requested from ones that have
    # literally never been touched. (Proper "complete" transition
    # requires the render Lambda to write back; tracked separately.)
    if project.status == "draft":
        project.status = "rendering"
        db.commit()

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


@router.get("/{project_id}/previews")
def list_previews(
    project_id: str,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> dict:
    """All slide preview URLs for the latest blueprint in one call.

    Avoids N round trips from the UI gallery — the preview modal needs
    every slide's presigned URL at once.
    """
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
    prefix = storage.output_prefix(tenant_id, project.id, bp.version)
    slides = []
    for i in range(1, len(bp.slides) + 1):
        key = f"{prefix}preview/slide-{i:02d}.jpg"
        slides.append({"slide_index": i, "url": storage.presign_download(key)})
    return {"slides": slides}


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
