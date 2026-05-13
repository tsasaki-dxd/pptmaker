"""
Integration tests for the async external integration API.

Flow under test:
  POST /api/v1/external/slides       → 202 + status=queued
  [blueprint_worker runs from SQS]   → BlueprintRow written, render SQS msg enqueued, project.status=rendering
  GET .../slides/{project_id}        → status=rendering
  [render Lambda completes]          → project.status=complete
  GET .../slides/{project_id}        → status=done + presigned URLs

Render Lambda + LLM are stubbed; blueprint_worker is driven manually
from the captured SQS message (same trick the existing test_e2e_flow
uses). ENV=local bypasses Cognito but emits a claim that satisfies the
slides:create scope check.
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# File-backed sqlite so the worker (driven manually) and the request
# thread see the same schema. :memory: is per-connection.
_DB_FILE_PATH = tempfile.mkstemp(suffix=".db")[1]
os.environ["ENV"] = "local"
os.environ["DB_URL"] = f"sqlite:///{_DB_FILE_PATH}"
os.environ["S3_BUCKET"] = "test-bucket"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["RENDER_QUEUE_URL"] = "https://sqs.us-east-1.amazonaws.com/111111111111/render-test"
os.environ["BLUEPRINT_QUEUE_URL"] = "https://sqs.us-east-1.amazonaws.com/111111111111/blueprint-test"
os.environ["ANTHROPIC_API_KEY"] = "test"

# Importing the worker triggers api.config.get_settings(); env must be
# set first. Ruff would prefer this with the other imports up top.
from api.blueprint_worker import handler as _bp_worker  # noqa: E402, I001


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
    _FAKE_SQS.messages.clear()
    from api.config import get_settings
    get_settings.cache_clear()

    with (
        patch("boto3.client", side_effect=_fake_boto3_client),
        patch("api.services.llm.LLMClient.blueprint", side_effect=_fake_blueprint),
        # template_analyzer hits S3 to inspect the uploaded .pptx; the
        # fake S3 doesn't have get_object. Stub it to return None so
        # the worker falls back to empty layouts (good enough for the
        # state-machine tests; render content is out of scope here).
        patch("api.blueprint_worker.analyze_template", return_value=None),
    ):
        from api.main import app
        from api.models.db import init_db

        with TestClient(app) as c:
            init_db()
            yield c


def _render_messages() -> list[dict]:
    return [m for m in _FAKE_SQS.messages if "render-test" in m["QueueUrl"]]


def _blueprint_messages() -> list[dict]:
    return [m for m in _FAKE_SQS.messages if "blueprint-test" in m["QueueUrl"]]


def _create_template(client: TestClient, name: str = "DXDesignSystem") -> str:
    r = client.post("/api/templates", params={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["template_id"]


def _drive_blueprint_worker() -> None:
    """Pop the most recent blueprint SQS message and feed it to the worker.

    Mirrors what the SQS event-source mapping does in prod. Caller is
    expected to have just POSTed /api/v1/external/slides — the blueprint
    message will be the latest entry in the captured SQS bus.
    """
    bp_msgs = _blueprint_messages()
    assert bp_msgs, "no blueprint SQS message captured"
    body = json.loads(bp_msgs[-1]["MessageBody"])
    _bp_worker({"Records": [{"body": json.dumps(body)}]}, None)


# -------- tests --------


def test_post_returns_202_and_queues_blueprint(client: TestClient) -> None:
    _create_template(client)

    r = client.post(
        "/api/v1/external/slides",
        json={
            "title": "週次レポート要約",
            "template_id": "DXDesignSystem",
            "report_markdown": "## summary\n- a",
        },
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["project_id"]
    assert body["pptx_url"] is None
    assert body["pdf_url"] is None
    assert body["preview_urls"] is None
    assert body["error"] is None

    # Exactly one blueprint job enqueued, with auto_render set so the
    # worker chains a render after blueprint commit.
    bp_msgs = _blueprint_messages()
    assert len(bp_msgs) == 1
    enqueued = json.loads(bp_msgs[0]["MessageBody"])
    assert enqueued["auto_render"] is True
    assert enqueued["project_id"] == body["project_id"]

    # No render job yet — that happens inside the worker.
    assert _render_messages() == []


def test_get_returns_queued_before_worker_runs(client: TestClient) -> None:
    _create_template(client)
    r = client.post(
        "/api/v1/external/slides",
        json={"title": "t", "template_id": "DXDesignSystem", "report_markdown": "x"},
    )
    project_id = r.json()["project_id"]

    r = client.get(f"/api/v1/external/slides/{project_id}")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "queued"


def test_worker_chains_render_and_flips_to_rendering(client: TestClient) -> None:
    _create_template(client)
    r = client.post(
        "/api/v1/external/slides",
        json={"title": "t", "template_id": "DXDesignSystem", "report_markdown": "x"},
    )
    project_id = r.json()["project_id"]

    _drive_blueprint_worker()

    # Worker submitted a render job and flipped the project status.
    render_msgs = _render_messages()
    assert len(render_msgs) == 1
    render_payload = json.loads(render_msgs[0]["MessageBody"])
    assert render_payload["project_id"] == project_id
    assert render_payload["blueprint"]["title"] == "週次レポート要約"

    # GET now reports "rendering".
    r = client.get(f"/api/v1/external/slides/{project_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rendering"
    assert body["pptx_url"] is None


def test_get_returns_done_with_urls_when_render_completes(client: TestClient) -> None:
    _create_template(client)
    r = client.post(
        "/api/v1/external/slides",
        json={"title": "t", "template_id": "DXDesignSystem", "report_markdown": "x"},
    )
    project_id = r.json()["project_id"]

    _drive_blueprint_worker()

    # Simulate the render Lambda finishing: flip project.status to
    # "complete" directly in the DB, same DB the GET handler reads.
    from api.models.db import ProjectRow, new_session
    db = new_session()
    try:
        row = db.query(ProjectRow).filter(ProjectRow.id == project_id).one()
        row.status = "complete"
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/v1/external/slides/{project_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done", body
    assert body["pptx_url"].endswith("output.pptx?sig=fake&op=get_object")
    assert body["pdf_url"].endswith("output.pdf?sig=fake&op=get_object")
    # FAKE_BLUEPRINT_JSON has 2 slides → 2 preview URLs.
    assert len(body["preview_urls"]) == 2
    assert body["error"] is None


def test_get_returns_error_when_render_fails(client: TestClient) -> None:
    _create_template(client)
    r = client.post(
        "/api/v1/external/slides",
        json={"title": "t", "template_id": "DXDesignSystem", "report_markdown": "x"},
    )
    project_id = r.json()["project_id"]

    _drive_blueprint_worker()

    from api.models.db import ProjectRow, new_session
    db = new_session()
    try:
        row = db.query(ProjectRow).filter(ProjectRow.id == project_id).one()
        row.status = "failed"
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/v1/external/slides/{project_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert "render failed" in body["error"]


def test_get_returns_error_when_blueprint_fails(client: TestClient) -> None:
    _create_template(client)
    r = client.post(
        "/api/v1/external/slides",
        json={"title": "t", "template_id": "DXDesignSystem", "report_markdown": "x"},
    )
    project_id = r.json()["project_id"]

    # Mark the blueprint job as failed directly — equivalent to the
    # worker's _mark_failed path after BlueprintBuildError retries.
    from api.models.db import BlueprintJobRow, new_session
    db = new_session()
    try:
        job = (
            db.query(BlueprintJobRow)
            .filter(BlueprintJobRow.project_id == project_id)
            .one()
        )
        job.status = "failed"
        job.error_message = "LLM returned unparseable JSON"
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/v1/external/slides/{project_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert body["error"] == "LLM returned unparseable JSON"


def test_get_unknown_project_returns_error(client: TestClient) -> None:
    r = client.get("/api/v1/external/slides/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert "project not found" in body["error"]


def test_post_unknown_template_returns_error_synchronously(client: TestClient) -> None:
    r = client.post(
        "/api/v1/external/slides",
        json={
            "title": "t",
            "template_id": "NonExistent",
            "report_markdown": "x",
        },
    )
    # The synchronous error path is the one exception to the
    # "always 202 from POST" rule: failing template lookup means we
    # never created a project, so there's nothing to poll. Return
    # 202 anyway with status=error so the response shape stays
    # uniform with the rest of the polling flow.
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "error"
    assert "template not found" in body["error"]
    # No SQS submission happened.
    assert _blueprint_messages() == []


def test_post_template_by_uuid(client: TestClient) -> None:
    template_id = _create_template(client, name="OtherTemplate")
    r = client.post(
        "/api/v1/external/slides",
        json={
            "title": "t",
            "template_id": template_id,
            "report_markdown": "x",
        },
    )
    assert r.status_code == 202
    assert r.json()["status"] == "queued"


def test_idempotency_key_header_accepted(client: TestClient) -> None:
    """Idempotency-Key header is accepted-but-ignored in Phase 1."""
    _create_template(client)
    r = client.post(
        "/api/v1/external/slides",
        json={
            "title": "idem",
            "template_id": "DXDesignSystem",
            "report_markdown": "x",
        },
        headers={"Idempotency-Key": "abc-123"},
    )
    assert r.status_code == 202
    assert r.json()["status"] == "queued"


def test_require_scope_rejects_missing_scope() -> None:
    """Unit-level check that the scope dep rejects tokens missing the scope."""
    from fastapi import HTTPException

    from api.auth import require_scope

    dep = require_scope("slideforge-api/slides:create")
    with pytest.raises(HTTPException) as exc:
        dep(user={"sub": "u1"})
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        dep(user={"sub": "u1", "scope": "aws.cognito.signin.user.admin"})
    assert exc.value.status_code == 403

    user = dep(
        user={
            "sub": "u1",
            "scope": "aws.cognito.signin.user.admin slideforge-api/slides:create",
        }
    )
    assert user["sub"] == "u1"

    permissive = require_scope("")
    assert permissive(user={"sub": "u1"}) == {"sub": "u1"}
