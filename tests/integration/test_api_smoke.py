"""
Minimal API smoke test using TestClient with env=local (bypasses Cognito).

Runs against an in-memory SQLite DB; upstream AWS / Claude calls are not
exercised here (covered by e2e separately).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ["ENV"] = "local"
os.environ["DB_URL"] = "sqlite:///:memory:"
os.environ["S3_BUCKET"] = "local-bucket"


@pytest.fixture()
def client() -> TestClient:
    from api.main import app
    from api.models.db import init_db

    with TestClient(app) as c:
        init_db()
        yield c


def test_health(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_auth_required(client: TestClient) -> None:
    res = client.post(
        "/api/projects",
        json={"name": "x", "template_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert res.status_code in (401, 403)


def test_openapi_spec_includes_core_endpoints(client: TestClient) -> None:
    res = client.get("/openapi.json")
    assert res.status_code == 200
    paths = res.json()["paths"]
    assert "/api/projects" in paths
    assert any(p.startswith("/api/templates") for p in paths)
