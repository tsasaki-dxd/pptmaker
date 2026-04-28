"""User-scoped projects + admin-only template deletion (data scope rules).

Projects are owner-scoped: only the Cognito ``sub`` that created a project
sees it (legacy NULL-owner rows stay visible to everyone for backward
compatibility). Template deletion requires Cognito ``admin`` group
membership.

The tests bypass Cognito by patching ``api.auth.cognito.verify_token``
directly, which lets us simulate two distinct users + a non-admin without
minting JWTs.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

_DB_FILE_PATH = tempfile.mkstemp(suffix=".db")[1]
os.environ["ENV"] = "local"
os.environ["DB_URL"] = f"sqlite:///{_DB_FILE_PATH}"
os.environ["S3_BUCKET"] = "test-bucket"
os.environ["AWS_REGION"] = "us-east-1"


class _FakeS3:
    def generate_presigned_url(self, op, Params, ExpiresIn):  # noqa: N803
        return f"https://{Params['Bucket']}.s3.amazonaws.com/{Params['Key']}?op={op}"

    def delete_object(self, Bucket, Key):  # noqa: N803
        return {}

    def list_objects_v2(self, **kwargs):
        return {"KeyCount": 0}


def _fake_boto3_client(service_name, **kwargs):
    if service_name == "s3":
        return _FakeS3()
    raise RuntimeError(f"unmocked boto3 service: {service_name}")


def _claims(sub: str, *, admin: bool = False) -> dict:
    return {
        "sub": sub,
        "tenant_id": "local-tenant",
        "cognito:groups": ["admin"] if admin else [],
    }


@contextmanager
def _as(claims: dict):
    """Override the Cognito mock so a single request runs as ``claims``."""
    # ENV=local short-circuits current_user, so patch that as well as
    # verify_token (the latter is what current_user delegates to).
    with (
        patch("api.auth.cognito.verify_token", return_value=claims),
        patch("api.auth.cognito.current_user", return_value=claims),
    ):
        yield


@pytest.fixture()
def client():
    from api.config import get_settings

    get_settings.cache_clear()

    with patch("boto3.client", side_effect=_fake_boto3_client):
        from api.main import app
        from api.models.db import init_db

        with TestClient(app) as c:
            init_db()
            yield c


def _make_template(client: TestClient) -> str:
    r = client.post("/api/templates", params={"name": "T"})
    assert r.status_code == 200, r.text
    return r.json()["template_id"]


def test_project_visible_only_to_owner(client: TestClient) -> None:
    template_id = _make_template(client)

    # Alice creates a project.
    with _as(_claims("user-alice")):
        r = client.post(
            "/api/projects",
            json={"name": "Alice's deck", "template_id": template_id},
        )
        assert r.status_code == 200, r.text
        alice_project = r.json()["id"]
        assert r.json()["owner_user_id"] == "user-alice"

    # Bob creates his own project + cannot see Alice's.
    with _as(_claims("user-bob")):
        r = client.post(
            "/api/projects",
            json={"name": "Bob's deck", "template_id": template_id},
        )
        assert r.status_code == 200, r.text
        bob_project = r.json()["id"]

        r = client.get("/api/projects")
        names = [p["name"] for p in r.json()]
        assert "Bob's deck" in names
        assert "Alice's deck" not in names

        # Direct GET of Alice's project returns 404 (do not leak existence).
        r = client.get(f"/api/projects/{alice_project}")
        assert r.status_code == 404

    # Alice still sees only her own.
    with _as(_claims("user-alice")):
        r = client.get("/api/projects")
        names = [p["name"] for p in r.json()]
        assert "Alice's deck" in names
        assert "Bob's deck" not in names

    # Sanity: Bob's project id was actually created.
    assert bob_project != alice_project


def test_legacy_null_owner_visible_to_all(client: TestClient) -> None:
    # Simulate a row predating the owner_user_id column by inserting one
    # with owner_user_id=NULL directly. Both users should see it in their
    # list (backward compat) until someone takes ownership.
    template_id = _make_template(client)

    from api.models.db import ProjectRow, new_session

    db = new_session()
    try:
        db.add(
            ProjectRow(
                tenant_id="local-tenant",
                owner_user_id=None,
                name="legacy",
                template_id=template_id,
            )
        )
        db.commit()
    finally:
        db.close()

    for sub in ("user-alice", "user-bob"):
        with _as(_claims(sub)):
            r = client.get("/api/projects")
            assert "legacy" in [p["name"] for p in r.json()]


def test_template_delete_requires_admin(client: TestClient) -> None:
    template_id = _make_template(client)

    # Non-admin: 403.
    with _as(_claims("user-non-admin", admin=False)):
        r = client.delete(f"/api/templates/{template_id}")
        assert r.status_code == 403, r.text

    # Admin: succeeds (template not in use, so the in_use guard passes).
    with _as(_claims("user-admin", admin=True)):
        r = client.delete(f"/api/templates/{template_id}")
        assert r.status_code == 200, r.text
        assert r.json()["deleted"] == template_id


def test_delete_project_cleans_revision_jobs_and_images(client: TestClient) -> None:
    """Regression: a project that exercised /revise or /images would leave
    RevisionJobRow / ImageAssetRow rows behind, both of which have a FK
    on projects.id. Without explicit cleanup, deleting the parent row hits
    IntegrityError and the API returns 500.

    SQLite doesn't enforce FKs by default so this test asserts the child
    rows are gone post-delete (production Postgres also requires this).
    """
    template_id = _make_template(client)

    with _as(_claims("user-alice")):
        r = client.post(
            "/api/projects",
            json={"name": "P", "template_id": template_id},
        )
        project_id = r.json()["id"]

    # Seed a RevisionJobRow + ImageAssetRow directly against the project.
    from api.models.db import ImageAssetRow, RevisionJobRow, new_session

    db = new_session()
    try:
        db.add(
            RevisionJobRow(
                project_id=project_id,
                tenant_id="local-tenant",
                instruction="test",
                status="complete",
            )
        )
        db.add(
            ImageAssetRow(
                tenant_id="local-tenant",
                project_id=project_id,
                s3_key=f"originals/local-tenant/{project_id}/asset-1.png",
                mime="image/png",
                bytes=1024,
            )
        )
        db.commit()
    finally:
        db.close()

    with _as(_claims("user-alice")):
        r = client.delete(f"/api/projects/{project_id}")
        assert r.status_code == 200, r.text

    # Both child tables must be empty for this project.
    db = new_session()
    try:
        assert (
            db.query(RevisionJobRow)
            .filter(RevisionJobRow.project_id == project_id)
            .count()
            == 0
        )
        assert (
            db.query(ImageAssetRow)
            .filter(ImageAssetRow.project_id == project_id)
            .count()
            == 0
        )
    finally:
        db.close()


def test_duplicate_assigns_new_owner(client: TestClient) -> None:
    """Duplicating someone else's project is impossible (404), and
    duplicating your own legacy NULL-owner project transfers ownership
    to the duplicator."""
    template_id = _make_template(client)

    # Legacy NULL-owner project visible to everyone.
    from api.models.db import ProjectRow, new_session

    db = new_session()
    try:
        legacy = ProjectRow(
            tenant_id="local-tenant",
            owner_user_id=None,
            name="shared",
            template_id=template_id,
        )
        db.add(legacy)
        db.commit()
        db.refresh(legacy)
        legacy_id = legacy.id
    finally:
        db.close()

    with _as(_claims("user-alice")):
        r = client.post(f"/api/projects/{legacy_id}/duplicate")
        assert r.status_code == 200, r.text
        new = r.json()
        assert new["owner_user_id"] == "user-alice"
        assert new["id"] != legacy_id

    # Bob can't see Alice's duplicate.
    with _as(_claims("user-bob")):
        r = client.get(f"/api/projects/{new['id']}")
        assert r.status_code == 404
