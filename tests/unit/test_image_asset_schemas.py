"""Pydantic validation tests for Phase 2 §6 ImageAsset schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.models.schemas import (
    ImageAsset,
    ImageAssetCommitRequest,
    ImageAssetCreateRequest,
    ImageAssetCreateResponse,
)

# --- ImageAssetCreateRequest -----------------------------------------------


def test_create_request_accepts_valid_png() -> None:
    r = ImageAssetCreateRequest(mime="image/png", bytes=1024)
    assert r.mime == "image/png"
    assert r.bytes == 1024


def test_create_request_accepts_jpeg_and_webp() -> None:
    assert ImageAssetCreateRequest(mime="image/jpeg", bytes=1).mime == "image/jpeg"
    assert ImageAssetCreateRequest(mime="image/webp", bytes=1).mime == "image/webp"


def test_create_request_rejects_bad_mime() -> None:
    with pytest.raises(ValidationError):
        ImageAssetCreateRequest(mime="image/gif", bytes=1024)


def test_create_request_rejects_zero_bytes() -> None:
    with pytest.raises(ValidationError):
        ImageAssetCreateRequest(mime="image/png", bytes=0)


def test_create_request_rejects_over_10mb() -> None:
    with pytest.raises(ValidationError):
        ImageAssetCreateRequest(mime="image/png", bytes=10_485_761)


def test_create_request_accepts_exactly_10mb() -> None:
    r = ImageAssetCreateRequest(mime="image/png", bytes=10_485_760)
    assert r.bytes == 10_485_760


# --- ImageAssetCreateResponse ----------------------------------------------


def test_create_response_round_trip() -> None:
    aid = uuid4()
    r = ImageAssetCreateResponse(
        asset_id=aid,
        upload_url="https://example.com/upload",
        fields={"key": "foo", "policy": "bar"},
    )
    assert r.asset_id == aid
    assert r.fields["key"] == "foo"


def test_create_response_requires_fields() -> None:
    with pytest.raises(ValidationError):
        ImageAssetCreateResponse(
            asset_id=uuid4(),
            upload_url="https://example.com/upload",
        )  # type: ignore[call-arg]


# --- ImageAssetCommitRequest -----------------------------------------------


def test_commit_request_accepts_valid_sha256() -> None:
    good = "a" * 64
    r = ImageAssetCommitRequest(checksum_sha256=good)
    assert r.checksum_sha256 == good


def test_commit_request_rejects_short_checksum() -> None:
    with pytest.raises(ValidationError):
        ImageAssetCommitRequest(checksum_sha256="a" * 63)


def test_commit_request_rejects_uppercase_hex() -> None:
    with pytest.raises(ValidationError):
        ImageAssetCommitRequest(checksum_sha256="A" * 64)


def test_commit_request_rejects_non_hex() -> None:
    with pytest.raises(ValidationError):
        ImageAssetCommitRequest(checksum_sha256="g" * 64)


# --- ImageAsset -------------------------------------------------------------


def test_image_asset_full_payload() -> None:
    a = ImageAsset(
        id=uuid4(),
        tenant_id="t-1",
        project_id=uuid4(),
        s3_key="tenants/t-1/projects/p/images/x",
        mime="image/png",
        bytes=2048,
        width_px=800,
        height_px=600,
        checksum_sha256="0" * 64,
        created_at=datetime.utcnow(),
    )
    assert a.width_px == 800
    assert a.checksum_sha256 == "0" * 64


def test_image_asset_allows_null_optional_fields() -> None:
    a = ImageAsset(
        id=uuid4(),
        tenant_id="t-1",
        project_id=uuid4(),
        s3_key="k",
        mime="image/jpeg",
        bytes=1,
        created_at=datetime.utcnow(),
    )
    assert a.width_px is None
    assert a.height_px is None
    assert a.checksum_sha256 is None


def test_image_asset_rejects_missing_required() -> None:
    with pytest.raises(ValidationError):
        ImageAsset(  # type: ignore[call-arg]
            id=uuid4(),
            tenant_id="t-1",
            project_id=uuid4(),
            mime="image/png",
            bytes=1,
            created_at=datetime.utcnow(),
        )
