"""S3 helpers (presigned URLs, object keys by tenant/project)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import boto3
from botocore.client import Config

from ..config import get_settings

log = logging.getLogger("slideforge.storage")


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
