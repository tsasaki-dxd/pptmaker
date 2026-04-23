"""S3 helpers (presigned URLs, object keys by tenant/project)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from ..config import get_settings

log = logging.getLogger("slideforge.storage")


# MIME -> file extension for the `originals/...` key prefix used by
# ImageAsset uploads (Phase 2 §6.3). Kept narrow on purpose: the
# Pydantic schema only accepts these three types, and S3 object keys
# must be deterministic from the validated mime.
_IMAGE_MIME_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpeg",
    "image/webp": ".webp",
}

# 7 days — max lifetime Amazon S3 accepts for SigV4 presigned URLs.
_IMAGE_UPLOAD_EXPIRES_SECONDS = 7 * 24 * 3600


def _image_extension_for_mime(mime: str) -> str:
    try:
        return _IMAGE_MIME_EXT[mime]
    except KeyError as e:
        raise ValueError(f"unsupported image mime: {mime!r}") from e


def image_original_key(tenant_id: str, project_id: str, asset_id: str, mime: str) -> str:
    """Canonical S3 key for an original (uploaded) ImageAsset.

    Shared between the presign helper and the router so the row's
    stored `s3_key` matches the key the browser actually POSTs to.
    """
    return f"originals/{tenant_id}/{project_id}/{asset_id}{_image_extension_for_mime(mime)}"


def _image_upload_client() -> tuple[Any, str]:
    """Boto3 S3 client + bucket name pinned to SigV4 for presigned POST.

    Mirrors the `Storage.__init__` pattern (SigV4 is required by KMS-SSE
    buckets). Extracted so the two image helpers below can share one
    session without instantiating the full `Storage` object — this also
    makes them trivial to monkey-patch in tests.
    """
    settings = get_settings()
    session = boto3.session.Session()
    client = session.client(
        "s3",
        region_name=settings.aws_region,
        config=Config(signature_version="s3v4"),
    )
    return client, settings.s3_bucket


def generate_image_upload_post(
    tenant_id: str,
    project_id: str,
    asset_id: str,
    mime: str,
    max_bytes: int,
) -> tuple[str, dict[str, str]]:
    """Build a presigned POST for browser -> S3 multipart upload.

    Returns `(url, fields)` straight from boto3's `generate_presigned_post`.
    The caller should echo `fields` back to the client unchanged so the
    browser's FormData includes every policy-signed field.
    """
    client, bucket = _image_upload_client()
    key = image_original_key(tenant_id, project_id, asset_id, mime)
    conditions: list[Any] = [
        ["content-length-range", 1, max_bytes],
        {"Content-Type": mime},
    ]
    resp = client.generate_presigned_post(
        Bucket=bucket,
        Key=key,
        Fields={"Content-Type": mime},
        Conditions=conditions,
        ExpiresIn=_IMAGE_UPLOAD_EXPIRES_SECONDS,
    )
    return resp["url"], resp["fields"]


def download_bytes(s3_path: str) -> bytes | None:
    """Fetch an S3 object's bytes. Returns None on 404/missing, raises on other errors.

    Accepts either a plain key (resolved against the configured default
    bucket) or an ``s3://bucket/key`` URI. Used by the render entry point
    to hand .pptx bytes to the lazy-slot-migration helper without
    instantiating the heavier ``Storage`` class.
    """
    client, default_bucket = _image_upload_client()
    if s3_path.startswith("s3://"):
        parsed = urlparse(s3_path)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
    else:
        bucket = default_bucket
        key = s3_path
    try:
        obj = client.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
            return None
        raise


def head_image_object(s3_key: str) -> dict[str, Any] | None:
    """Return the S3 HeadObject response for `s3_key`, or None if missing.

    Used by the ImageAsset commit endpoint to verify that the browser
    actually completed the upload before we mark the row committed.
    Any 404 / NoSuchKey / NotFound collapses to None; other errors
    (permissions, throttling) propagate so the caller sees them.
    """
    client, bucket = _image_upload_client()
    try:
        return client.head_object(Bucket=bucket, Key=s3_key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
            return None
        raise


@dataclass
class PresignedUpload:
    url: str
    s3_uri: str
    key: str


class Storage:
    def __init__(self) -> None:
        self.settings = get_settings()
        # Force SigV4. The artifacts bucket is KMS-encrypted with a CMK,
        # and S3 rejects presigned PUTs signed with SigV2 against
        # KMS-SSE buckets:
        #   InvalidArgument: Requests specifying Server Side Encryption
        #   with AWS KMS managed keys require AWS Signature Version 4.
        # boto3's default signature version for presigned URLs varies by
        # region/version, so pin it here.
        self.s3 = boto3.client(
            "s3",
            region_name=self.settings.aws_region,
            config=Config(signature_version="s3v4"),
        )
        self.bucket = self.settings.s3_bucket

    def presign_upload(self, key: str, expires: int = 900, content_type: str | None = None) -> PresignedUpload:
        params = {"Bucket": self.bucket, "Key": key}
        if content_type:
            params["ContentType"] = content_type
        url = self.s3.generate_presigned_url("put_object", Params=params, ExpiresIn=expires)
        return PresignedUpload(url=url, s3_uri=f"s3://{self.bucket}/{key}", key=key)

    def presign_download(self, key: str, expires: int = 900) -> str:
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires,
        )

    def template_key(self, tenant_id: str, template_id: str) -> str:
        return f"tenants/{tenant_id}/templates/{template_id}.pptx"

    def output_prefix(self, tenant_id: str, project_id: str, version: int) -> str:
        return f"tenants/{tenant_id}/projects/{project_id}/outputs/v{version}/"

    def project_prefix(self, tenant_id: str, project_id: str) -> str:
        return f"tenants/{tenant_id}/projects/{project_id}/"

    def as_uri(self, key: str) -> str:
        return f"s3://{self.bucket}/{key}"

    def delete_prefix(self, prefix: str) -> int:
        """Delete every object under `prefix`. Returns the count deleted.

        Used by project delete to clean up all rendered outputs for a
        project without enumerating versions individually. Best-effort:
        a partial failure logs but doesn't raise."""
        deleted = 0
        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                contents = page.get("Contents") or []
                if not contents:
                    continue
                # delete_objects takes up to 1000 keys per call; pages
                # already cap at 1000 so one call per page is fine.
                self.s3.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": [{"Key": o["Key"]} for o in contents]},
                )
                deleted += len(contents)
        except Exception:
            log.exception("delete_prefix failed prefix=%s", prefix)
        return deleted
