"""
End-to-end integration test for the whole backend API flow.

Uses:
  - SQLite in-memory for the DB
  - lightweight in-place fakes for boto3 S3/SQS clients
  - a stub LLMClient so no real Anthropic call is made
  - ENV=local to short-circuit Cognito JWT verification

Covers: create template -> create project -> create blueprint ->
revise blueprint -> request render -> fetch preview/export URLs.
"""

from __future__ import annotations

import json as _json
import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Use a file-backed sqlite so connections made by different requests share
# the same schema. `:memory:` creates a fresh DB per connection, which means
# init_db's CREATE TABLE doesn't survive to the next request.
_DB_FILE_PATH = tempfile.mkstemp(suffix=".db")[1]
os.environ["ENV"] = "local"
os.environ["DB_URL"] = f"sqlite:///{_DB_FILE_PATH}"
os.environ["S3_BUCKET"] = "test-bucket"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["RENDER_QUEUE_URL"] = "https://sqs.us-east-1.amazonaws.com/111111111111/render-test"
os.environ["BLUEPRINT_QUEUE_URL"] = "https://sqs.us-east-1.amazonaws.com/111111111111/blueprint-test"
os.environ["ANTHROPIC_API_KEY"] = "test"  # prevents Secrets Manager lookup

# Imported after the env-var setup above so api.config sees the test
# values (get_settings is lru_cached on first access). Ruff would prefer
# this up top with the other imports; it can't go there.
from api.blueprint_worker import handler as _bp_worker  # noqa: E402, I001


FAKE_BLUEPRINT_JSON = """
{
  "title": "DX推進ご提案書",
  "slides": [
    {"index": 1, "layout": "cover", "content": {"title": "DX推進ご提案"}},
    {"index": 2, "layout": "toc", "content": {"items": ["現状", "提案", "費用"]}},
    {
      "index": 3,
      "layout": "content",
      "figure_type": "bullet_list",
      "content": {"title": "課題", "items": ["データ分散", "属人化", "レガシーシステム"]}
    }
  ]
}
"""

FAKE_PATCH_JSON = """
[{"op": "replace", "path": "/title", "value": "DX推進ご提案書（更新版）"}]
"""


class _FakeLLMResult:
    def __init__(self, text: str):
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


def _fake_revision(*args, **kwargs):  # type: ignore[no-untyped-def]
    return _FakeLLMResult(FAKE_PATCH_JSON)


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
    from api.config import get_settings
    get_settings.cache_clear()

    with (
        patch("boto3.client", side_effect=_fake_boto3_client),
        patch("api.services.llm.LLMClient.blueprint", side_effect=_fake_blueprint),
        patch("api.services.llm.LLMClient.revision_patch", side_effect=_fake_revision),
    ):
        from api.main import app
        from api.models.db import init_db

        with TestClient(app) as c:
            init_db()
            yield c


def test_full_flow(client: TestClient) -> None:
    # 1. create template
    r = client.post("/api/templates", params={"name": "DXデザインシステム"})
    assert r.status_code == 200, r.text
    t = r.json()
    template_id = t["template_id"]
    assert t["upload_url"].startswith("https://")

    # 2. get template (verify it was stored)
    r = client.get(f"/api/templates/{template_id}")
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "DXデザインシステム"

    # 3. create project
    r = client.post("/api/projects", json={"name": "A社向け", "template_id": template_id})
    assert r.status_code == 200, r.text
    project = r.json()
    project_id = project["id"]

    # 4. create blueprint job (async). API enqueues + returns 202.
    r = client.post(
        f"/api/projects/{project_id}/blueprint",
        json={
            "intent": "A社向けのDX推進提案書。現状課題、提案、費用、スケジュールを含む",
            "required_sections": ["課題認識", "提案概要", "費用"],
            "mode": "freeform",
        },
    )
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] == "pending"
    assert job["blueprint_id"] is None
    job_id = job["job_id"]

    # Drive the worker directly — SQS is a fake in this test, so nothing
    # would pick the message up otherwise.
    bp_msg = _json.loads(_FAKE_SQS.messages[-1]["MessageBody"])
    _bp_worker({"Records": [{"body": _json.dumps(bp_msg)}]}, None)

    # Poll the job: worker just ran, so it should already be complete.
    r = client.get(f"/api/projects/{project_id}/blueprint/job/{job_id}")
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["status"] == "complete", done
    assert done["blueprint_id"]

    # 5. get latest blueprint
    r = client.get(f"/api/projects/{project_id}/blueprint")
    assert r.status_code == 200, r.text
    bp = r.json()
    assert bp["id"] == done["blueprint_id"]
    assert bp["version"] == 1
    assert bp["title"].startswith("DX")
    assert len(bp["slides"]) == 3

    # 6. revise (patch via LLM mock)
    r = client.post(
        f"/api/projects/{project_id}/revise",
        json={"instruction": "タイトルを DX推進ご提案書（更新版） に変えて"},
    )
    assert r.status_code == 200, r.text
    rev = r.json()
    assert rev["applied"] is True
    assert isinstance(rev["patch"], list)

    # new blueprint should be version 2
    r = client.get(f"/api/projects/{project_id}/blueprint")
    assert r.status_code == 200, r.text
    latest = r.json()
    assert latest["version"] == 2

    # 7. request render (queued via SQS stub)
    sqs_before = len(_FAKE_SQS.messages)
    r = client.post(f"/api/projects/{project_id}/render")
    assert r.status_code == 200, r.text
    rj = r.json()
    assert rj["status"] == "queued"
    assert rj["blueprint_id"] == latest["id"]
    assert len(_FAKE_SQS.messages) == sqs_before + 1

    # 8. preview URL (S3 presigned)
    r = client.get(f"/api/projects/{project_id}/preview/1")
    assert r.status_code == 200, r.text
    assert r.json()["url"].startswith("https://")

    # 9. export URL
    r = client.get(f"/api/projects/{project_id}/export", params={"format": "pptx"})
    assert r.status_code == 200, r.text
    assert r.json()["format"] == "pptx"


def test_bad_format_rejected(client: TestClient) -> None:
    r = client.post("/api/templates", params={"name": "T"})
    template_id = r.json()["template_id"]
    r = client.post("/api/projects", json={"name": "P", "template_id": template_id})
    project_id = r.json()["id"]
    client.post(
        f"/api/projects/{project_id}/blueprint",
        json={"intent": "test", "required_sections": [], "mode": "freeform"},
    )

    r = client.get(f"/api/projects/{project_id}/export", params={"format": "invalid"})
    assert r.status_code == 400


def test_blueprint_before_project_404(client: TestClient) -> None:
    r = client.get("/api/projects/00000000-0000-0000-0000-000000000000/blueprint")
    assert r.status_code == 404


def test_revise_without_blueprint_400(client: TestClient) -> None:
    r = client.post("/api/templates", params={"name": "T"})
    template_id = r.json()["template_id"]
    r = client.post("/api/projects", json={"name": "P", "template_id": template_id})
    project_id = r.json()["id"]

    r = client.post(
        f"/api/projects/{project_id}/revise",
        json={"instruction": "何か変えて"},
    )
    assert r.status_code == 400


def test_duplicate_project_copies_blueprint(client: TestClient) -> None:
    r = client.post("/api/templates", params={"name": "T-dup"})
    template_id = r.json()["template_id"]
    r = client.post("/api/projects", json={"name": "Original", "template_id": template_id})
    project_id = r.json()["id"]

    r = client.post(
        f"/api/projects/{project_id}/blueprint",
        json={"intent": "テスト", "required_sections": [], "mode": "freeform"},
    )
    assert r.status_code == 202
    bp_msg = _json.loads(_FAKE_SQS.messages[-1]["MessageBody"])
    _bp_worker({"Records": [{"body": _json.dumps(bp_msg)}]}, None)

    r = client.post(f"/api/projects/{project_id}/duplicate")
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["id"] != project_id
    assert new["name"] == "Original (copy)"
    assert new["status"] == "draft"

    # The new project gets its own copy of the source's latest blueprint.
    r = client.get(f"/api/projects/{new['id']}/blueprint")
    assert r.status_code == 200, r.text
    bp = r.json()
    assert bp["version"] == 1
    assert len(bp["slides"]) == 3  # FAKE_BLUEPRINT_JSON has 3 slides


def test_delete_project_cascades(client: TestClient) -> None:
    r = client.post("/api/templates", params={"name": "T-del"})
    template_id = r.json()["template_id"]
    r = client.post("/api/projects", json={"name": "ToDelete", "template_id": template_id})
    project_id = r.json()["id"]

    # Run a blueprint job so there's a BlueprintRow + BlueprintJobRow to clean up.
    r = client.post(
        f"/api/projects/{project_id}/blueprint",
        json={"intent": "テスト", "required_sections": [], "mode": "freeform"},
    )
    bp_msg = _json.loads(_FAKE_SQS.messages[-1]["MessageBody"])
    _bp_worker({"Records": [{"body": _json.dumps(bp_msg)}]}, None)

    r = client.delete(f"/api/projects/{project_id}")
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == project_id

    # Subsequent reads should 404.
    r = client.get(f"/api/projects/{project_id}")
    assert r.status_code == 404
    r = client.get(f"/api/projects/{project_id}/blueprint")
    assert r.status_code == 404
