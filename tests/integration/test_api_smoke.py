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


def test_openapi_exposes_auth_dependency() -> None:
    """ENV=local bypasses Cognito for tests; verify that the auth dependency
    is still declared on protected routes (so prod will enforce it)."""
    from api.main import app

    with TestClient(app) as c:
        spec = c.get("/openapi.json").json()

    # The POST /api/projects route should have a security-relevant parameter
    # (Authorization header) in its operation.
    post_projects = spec["paths"]["/api/projects"]["post"]
    params = post_projects.get("parameters", [])
    header_names = [p["name"].lower() for p in params if p.get("in") == "header"]
    assert "authorization" in header_names


def test_openapi_spec_includes_core_endpoints(client: TestClient) -> None:
    res = client.get("/openapi.json")
    assert res.status_code == 200
    paths = res.json()["paths"]
    assert "/api/projects" in paths
    assert any(p.startswith("/api/templates") for p in paths)
