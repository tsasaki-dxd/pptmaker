"""Template upload / profile endpoints."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_tenant
from ..models.db import ProjectRow, TemplateProfileRow, get_session
from ..models.schemas import TemplateCreateResponse, TemplateProfile
from ..services.storage import Storage

log = logging.getLogger("slideforge.templates")

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("", response_model=list[TemplateProfile])
def list_templates(
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> list[TemplateProfile]:
    rows = (
        db.query(TemplateProfileRow)
        .filter(TemplateProfileRow.tenant_id == tenant_id)
        .order_by(TemplateProfileRow.created_at.desc())
        .all()
    )
    return [
        TemplateProfile(
            id=r.id,
            tenant_id=r.tenant_id,
            name=r.name,
            original_s3_path=r.original_s3_path,
            design_tokens=r.design_tokens,
            layouts=r.layouts,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("", response_model=TemplateCreateResponse)
def create_template(
    name: str,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> TemplateCreateResponse:
    storage = Storage()
    template_id = str(uuid4())
    key = storage.template_key(tenant_id, template_id)

    row = TemplateProfileRow(
        id=template_id,
        tenant_id=tenant_id,
        name=name,
        original_s3_path=storage.as_uri(key),
        design_tokens={},
        layouts=[],
    )
    db.add(row)
    db.commit()

    presigned = storage.presign_upload(
        key,
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    return TemplateCreateResponse(template_id=template_id, upload_url=presigned.url)


@router.get("/{template_id}", response_model=TemplateProfile)
def get_template(
    template_id: str,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> TemplateProfile:
    row = (
        db.query(TemplateProfileRow)
        .filter(TemplateProfileRow.id == template_id, TemplateProfileRow.tenant_id == tenant_id)
        .one()
    )
    return TemplateProfile(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        original_s3_path=row.original_s3_path,
        design_tokens=row.design_tokens,
        layouts=row.layouts,
        created_at=row.created_at,
    )


@router.delete("/{template_id}")
def delete_template(
    template_id: str,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> dict:
    row = (
        db.query(TemplateProfileRow)
        .filter(TemplateProfileRow.id == template_id, TemplateProfileRow.tenant_id == tenant_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "template not found")

    # Refuse if any project still references this template, otherwise
    # those projects end up with a dangling template_id FK.
    in_use = (
        db.query(ProjectRow)
        .filter(ProjectRow.template_id == template_id)
        .count()
    )
    if in_use > 0:
        raise HTTPException(
            409,
            f"template is used by {in_use} project(s); delete those first",
        )

    storage = Storage()
    key = storage.template_key(tenant_id, template_id)
    try:
        storage.s3.delete_object(Bucket=storage.bucket, Key=key)
    except Exception:
        # S3 object may already be gone if the upload failed; don't let
        # that block the DB row deletion.
        log.exception("delete_object failed key=%s", key)

    db.delete(row)
    db.commit()
    return {"deleted": template_id}
