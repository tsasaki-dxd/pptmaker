"""Unit tests for `services.storage.generate_image_upload_post`.

We stub boto3 via `unittest.mock` so these tests are hermetic (no real
AWS calls, no moto dependency). The stub captures every argument
`generate_presigned_post` is called with and returns a deterministic
fake response, which lets us assert on Bucket/Key/Conditions/Fields
without signing anything.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from api.services import storage


@pytest.fixture
def fake_s3_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch the private client factory so no real boto3 session is created."""
    client = MagicMock()
    client.generate_presigned_post.return_value = {
        "url": "https://s3.example.amazonaws.com/test-bucket",
        "fields": {
            "key": "PLACEHOLDER",
            "Content-Type": "PLACEHOLDER",
            "policy": "b64policy",
            "x-amz-signature": "sig",
        },
    }
    monkeypatch.setattr(
        storage, "_image_upload_client", lambda: (client, "test-bucket")
    )
    return client


# --- image_original_key / extension mapping --------------------------------


def test_image_original_key_png() -> None:
    k = storage.image_original_key("t1", "p1", "a1", "image/png")
    assert k == "originals/t1/p1/a1.png"


def test_image_original_key_jpeg() -> None:
    assert storage.image_original_key("t1", "p1", "a1", "image/jpeg").endswith(".jpeg")


def test_image_original_key_webp() -> None:
    assert storage.image_original_key("t1", "p1", "a1", "image/webp").endswith(".webp")


def test_image_original_key_rejects_unknown_mime() -> None:
    with pytest.raises(ValueError, match="unsupported image mime"):
        storage.image_original_key("t1", "p1", "a1", "image/gif")


# --- generate_image_upload_post --------------------------------------------


def test_generate_image_upload_post_returns_url_and_fields(
    fake_s3_client: MagicMock,
) -> None:
    url, fields = storage.generate_image_upload_post(
        tenant_id="tenant-42",
        project_id="project-7",
        asset_id="asset-abc",
        mime="image/png",
        max_bytes=1_000_000,
    )
    assert url == "https://s3.example.amazonaws.com/test-bucket"
    assert "policy" in fields
    assert fields["x-amz-signature"] == "sig"


def test_generate_image_upload_post_uses_expected_key_and_bucket(
    fake_s3_client: MagicMock,
) -> None:
    storage.generate_image_upload_post(
        tenant_id="tenant-42",
        project_id="project-7",
        asset_id="asset-abc",
        mime="image/png",
        max_bytes=1_000_000,
    )
    kwargs = fake_s3_client.generate_presigned_post.call_args.kwargs
    assert kwargs["Bucket"] == "test-bucket"
    assert kwargs["Key"] == "originals/tenant-42/project-7/asset-abc.png"


def test_generate_image_upload_post_sets_content_type_condition(
    fake_s3_client: MagicMock,
) -> None:
    storage.generate_image_upload_post(
        tenant_id="t",
        project_id="p",
        asset_id="a",
        mime="image/webp",
        max_bytes=500,
    )
    kwargs = fake_s3_client.generate_presigned_post.call_args.kwargs
    conditions: list[Any] = kwargs["Conditions"]
    # The Content-Type condition appears both as a dict in Conditions
    # (so S3 enforces it) and mirrored in Fields (so the browser sends it).
    assert {"Content-Type": "image/webp"} in conditions
    assert kwargs["Fields"]["Content-Type"] == "image/webp"


def test_generate_image_upload_post_passes_max_bytes_into_content_length_range(
    fake_s3_client: MagicMock,
) -> None:
    storage.generate_image_upload_post(
        tenant_id="t",
        project_id="p",
        asset_id="a",
        mime="image/jpeg",
        max_bytes=7_654_321,
    )
    kwargs = fake_s3_client.generate_presigned_post.call_args.kwargs
    ranges = [c for c in kwargs["Conditions"] if isinstance(c, list) and c[0] == "content-length-range"]
    assert ranges == [["content-length-range", 1, 7_654_321]]


def test_generate_image_upload_post_expiry_is_seven_days(
    fake_s3_client: MagicMock,
) -> None:
    storage.generate_image_upload_post(
        tenant_id="t",
        project_id="p",
        asset_id="a",
        mime="image/png",
        max_bytes=10,
    )
    kwargs = fake_s3_client.generate_presigned_post.call_args.kwargs
    assert kwargs["ExpiresIn"] == 7 * 24 * 3600


def test_generate_image_upload_post_rejects_unknown_mime(
    fake_s3_client: MagicMock,
) -> None:
    with pytest.raises(ValueError, match="unsupported image mime"):
        storage.generate_image_upload_post(
            tenant_id="t",
            project_id="p",
            asset_id="a",
            mime="image/gif",
            max_bytes=10,
        )
    # Should have failed before hitting boto3.
    fake_s3_client.generate_presigned_post.assert_not_called()
