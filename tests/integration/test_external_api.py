"""
Integration tests for POST /api/v1/external/slides.

Covers:
  - happy path with wait=False (project + blueprint persisted, render
    submitted to SQS, no polling)
  - happy path with wait=True (RenderQueue stub flips project status to
    "complete" so the wait loop returns presigned URLs)
  - template lookup by display name (default report_bot input)
  - bad template returns status="error" instead of a 4xx so the caller's
    branching logic stays simple

The Cognito JWKS path is bypassed via ENV=local (api.auth.cognito
returns a stub claim dict that satisfies the slides:create scope
requirement). A separate unit test covers the scope check itself.
"""

from __future__ import annotations

import json as _json
import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# File-backed sqlite so the request thread + the wait_for_render thread
# see the same schema. (:memory: is per-connection.)
_DB_FILE_PATH = tempfile.mkstemp(suffix=".db")[1]
os.environ["ENV"] = "local"
os.environ["DB_URL"] = f"sqlite:///{_DB_FILE_PATH}"
os.environ["S3_BUCKET"] = "test-bucket"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["RENDER_QUEUE_URL"] = "https://sqs.us-east-1.amazonaws.com/111111111111/render-test"
os.environ["BLUEPRINT_QUEUE_URL"] = "https://sqs.us-east-1.amazonaws.com/111111111111/blueprint-test"
os.environ["ANTHROPIC_API_KEY"] = "test"


FAKE_BLUEPRINT_JSON = """
{
  "title": "週次レポート要約",
  "slides": [
    {"index": 1, "layout": "cover", "content": {"title": "週次レポート要約"}},
    {"index": 2, "layout": "content", "figure_type": "bullet_list",
     "content": {"title": "主要トピック", "items": ["A", "B", "C"]}}
  ]
}
"""


class _FakeLLMResult:
    def __init__(self, text: str) -> None:
        self.text = text
        self.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }
        self.model = "claude-sonnet-4-6"


def _fake_blueprint(*args, **kwargs):  # type: ignore[no-untyped-def]
    return _FakeLLMResult(FAKE_BLUEPRINT_JSON)


class _FakeS3:
    def generate_presigned_url(self, op: str, Params: dict, ExpiresIn: int) -> str:  # noqa: N803
        bucket = Params["Bucket"]
        key = Params["Key"]
        return f"https://{bucket}.s3.amazonaws.com/{key}?sig=fake&op={op}"


class _FakeSqs:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def send_message(self, QueueUrl: str, MessageBody: str) -> dict:  # noqa: N803
        self.messages.append({"QueueUrl": QueueUrl, "MessageBody": MessageBody})
        return {"MessageId": f"mid-{len(self.messages)}"}


_FAKE_SQS = _FakeSqs()


def _fake_boto3_client(service_name: str, **kwargs):  # type: ignore[no-untyped-def]
    if service_name == "s3":
        return _FakeS3()
    if service_name == "sqs":
        return _FAKE_SQS
    raise RuntimeError(f"unmocked boto3 service: {service_name}")


@pytest.fixture()
def client():  # type: ignore[no-untyped-def]
    # Reset the SQS stub between tests so message counts don't leak.
    _FAKE_SQS.messages.clear()
    from api.config import get_settings
    get_settings.cache_clear()

    with (
        patch("boto3.client", side_effect=_fake_boto3_client),
        patch("api.services.llm.LLMClient.blueprint", side_effect=_fake_blueprint),
        # template_analyzer.analyze_template hits S3 to download the
        # uploaded .pptx; the file doesn't actually exist in the fake.
        # The router falls back to an empty layouts list when analyze
        # returns None, so stub it that way.
        patch("api.routers.external.analyze_template", return_value=None),
    ):
        from api.main import app
        from api.models.db import init_db

        with TestClient(app) as c:
            init_db()
            yield c


def _create_template(client: TestClient, name: str = "DXDesignSystem") -> str:
    """Helper: create a template the M2M endpoint can look up by name."""
    r = client.post("/api/templates", params={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["template_id"]


def test_external_slides_wait_false(client: TestClient) -> None:
    _create_template(client)

    r = client.post(
        "/api/v1/external/slides",
        json={
            "title": "週次レポート要約",
            "template_id": "DXDesignSystem",
            "report_markdown": "## 今週の出来事\n- A\n- B\n- C",
            "source_url": "https://example.com/weekly/2026-05",
            "wait": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["project_id"]
    # wait=False short-circuits before submitting the render job — only
    # the blueprint was generated, no SQS render submission.
    render_msgs = [m for m in _FAKE_SQS.messages if "render-test" in m["QueueUrl"]]
    assert render_msgs == []

    # The project + blueprint must actually be persisted so a follow-up
    # GET /api/projects/{id} returns them.
    r = client.get(f"/api/projects/{body['project_id']}/blueprint")
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "週次レポート要約"


def test_external_slides_wait_true_returns_urls(client: TestClient) -> None:
    _create_template(client)

    # Simulate the render Lambda completing: replace RenderQueue.submit
    # so it flips the row to "complete" in the same DB the wait loop
    # polls against. That way the wait loop terminates inside the test
    # without an actual SQS consumer.
    from api.models.db import ProjectRow, new_session
    from api.services.queue import RenderQueue

    original_submit = RenderQueue.submit

    def _submit_and_complete(self, job: dict) -> str:
        result = original_submit(self, job)
        db = new_session()
        try:
            row = (
                db.query(ProjectRow)
                .filter(ProjectRow.id == job["project_id"])
                .one()
            )
            row.status = "complete"
            db.commit()
        finally:
            db.close()
        return result

    with patch.object(RenderQueue, "submit", _submit_and_complete):
        r = client.post(
            "/api/v1/external/slides",
            json={
                "title": "週次レポート要約",
                "template_id": "DXDesignSystem",
                "report_markdown": "## summary\n- a",
                "wait": True,
                # Shrink the timeout so the test fails fast if the
                # stub isn't doing its job — real wait_for_render
                # backoff is 2s, 3s, …, so 30s gives plenty of room
                # while still catching a stuck poller.
                "timeout_sec": 30,
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done", body
    assert body["pptx_url"].endswith("output.pptx?sig=fake&op=get_object")
    assert body["pdf_url"].endswith("output.pdf?sig=fake&op=get_object")
    # FAKE_BLUEPRINT_JSON has 2 slides → 2 preview URLs.
    assert len(body["preview_urls"]) == 2


def test_external_slides_unknown_template_returns_error_status(client: TestClient) -> None:
    # No template created — name lookup should fail.
    r = client.post(
        "/api/v1/external/slides",
        json={
            "title": "test",
            "template_id": "NonExistent",
            "report_markdown": "body",
            "wait": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "error"
    assert "template not found" in body["error"]


def test_external_slides_template_by_uuid(client: TestClient) -> None:
    template_id = _create_template(client, name="OtherTemplate")
    r = client.post(
        "/api/v1/external/slides",
        json={
            "title": "uuid path",
            "template_id": template_id,
            "report_markdown": "body",
            "wait": False,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"


def test_external_slides_idempotency_header_accepted(client: TestClient) -> None:
    """Idempotency-Key is accepted-but-ignored in Phase 1.

    Verifies the header doesn't trigger a validation error — when we
    add dedupe in a later phase the integration test can be tightened
    without touching report_bot.
    """
    _create_template(client)
    r = client.post(
        "/api/v1/external/slides",
        json={
            "title": "idem",
            "template_id": "DXDesignSystem",
            "report_markdown": "body",
            "wait": False,
        },
        headers={"Idempotency-Key": "abc-123"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"


def test_require_scope_rejects_missing_scope() -> None:
    """Direct unit test of the scope dependency.

    ENV=local can't exercise this — the bypass returns a claim dict
    that already includes the required scope — so we call the
    dependency factory with a hand-crafted user dict instead. Confirms
    a token without the slides:create scope is denied.
    """
    from fastapi import HTTPException

    from api.auth import require_scope

    dep = require_scope("slideforge-api/slides:create")

    # Missing scope → 403.
    with pytest.raises(HTTPException) as exc:
        dep(user={"sub": "u1"})
    assert exc.value.status_code == 403

    # Wrong scope → still 403.
    with pytest.raises(HTTPException) as exc:
        dep(user={"sub": "u1", "scope": "aws.cognito.signin.user.admin"})
    assert exc.value.status_code == 403

    # Right scope (among others) → returns the user.
    user = dep(
        user={
            "sub": "u1",
            "scope": "aws.cognito.signin.user.admin slideforge-api/slides:create",
        }
    )
    assert user["sub"] == "u1"

    # Empty required_scope → check is disabled.
    permissive = require_scope("")
    assert permissive(user={"sub": "u1"}) == {"sub": "u1"}


# Quiet "imported but unused" when this module is loaded in isolation —
# the _json import is required by some sibling tests in the package.
_ = _json
