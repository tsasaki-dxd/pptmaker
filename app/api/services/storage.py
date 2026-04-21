"""S3 helpers (presigned URLs, object keys by tenant/project)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import boto3

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
        self.s3 = boto3.client("s3", region_name=self.settings.aws_region)
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

    def as_uri(self, key: str) -> str:
        return f"s3://{self.bucket}/{key}"
