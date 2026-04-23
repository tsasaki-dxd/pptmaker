"""ImageAsset endpoints — scaffold for Phase 2 §6.

S3 presigned-POST and ZIP-embedding land in a later PR; this module
delivers the data model and API surface only.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_tenant
from ..models.db import ImageAssetRow, ProjectRow, get_session
from ..models.schemas import (
    ImageAsset,
    ImageAssetCommitRequest,
    ImageAssetCreateRequest,
    ImageAssetCreateResponse,
)

log = logging.getLogger("slideforge.images")

router = APIRouter(prefix="/api/projects", tags=["images"])


@router.post("/{project_id}/images", response_model=ImageAssetCreateResponse)
def create_image_asset(
    project_id: str,
    body: ImageAssetCreateRequest,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> ImageAssetCreateResponse:
    """Allocate an image asset row and return a (placeholder) presigned POST.

    The client uploads the bytes directly to S3, then calls /commit with
    the SHA-256 to mark the asset usable.
    """
    _load_project(db, project_id, tenant_id)

    asset_id = str(uuid4())
    s3_key = f"tenants/{tenant_id}/projects/{project_id}/images/{asset_id}"
    row = ImageAssetRow(
        id=asset_id,
        tenant_id=tenant_id,
        project_id=project_id,
        s3_key=s3_key,
        mime=body.mime,
        bytes=body.bytes,
        width_px=None,
        height_px=None,
        checksum_sha256=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # TODO(phase2.3): replace with real S3 presigned POST via Storage.
    upload_url = "https://example.invalid/presigned-upload-placeholder"
    fields: dict[str, str] = {"key": s3_key}

    return ImageAssetCreateResponse(
        asset_id=row.id,
        upload_url=upload_url,
        fields=fields,
    )


@router.post(
    "/{project_id}/images/{asset_id}/commit",
    response_model=ImageAsset,
)
def commit_image_asset(
    project_id: str,
    asset_id: str,
    body: ImageAssetCommitRequest,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> ImageAsset:
    """Mark an image asset committed by storing its SHA-256 checksum."""
    row = _load_asset(db, project_id, asset_id, tenant_id)
    row.checksum_sha256 = body.checksum_sha256
    db.commit()
    db.refresh(row)
    return _to_schema(row)


@router.get(
    "/{project_id}/images/{asset_id}",
    response_model=ImageAsset,
)
def get_image_asset(
    project_id: str,
    asset_id: str,
    tenant_id: str = Depends(require_tenant),
    db: Session = Depends(get_session),
) -> ImageAsset:
    row = _load_asset(db, project_id, asset_id, tenant_id)
    return _to_schema(row)


def _load_project(db: Session, project_id: str, tenant_id: str) -> ProjectRow:
    row = (
        db.query(ProjectRow)
        .filter(ProjectRow.id == project_id, ProjectRow.tenant_id == tenant_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "project not found")
    return row


def _load_asset(
    db: Session, project_id: str, asset_id: str, tenant_id: str
) -> ImageAssetRow:
    row = (
        db.query(ImageAssetRow)
        .filter(
            ImageAssetRow.id == asset_id,
            ImageAssetRow.project_id == project_id,
            ImageAssetRow.tenant_id == tenant_id,
        )
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "image asset not found")
    return row


def _to_schema(row: ImageAssetRow) -> ImageAsset:
    return ImageAsset(
        id=row.id,
        tenant_id=row.tenant_id,
        project_id=row.project_id,
        s3_key=row.s3_key,
        mime=row.mime,
        bytes=row.bytes,
        width_px=row.width_px,
        height_px=row.height_px,
        checksum_sha256=row.checksum_sha256,
        created_at=row.created_at,
    )
