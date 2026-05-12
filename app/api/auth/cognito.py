"""
Cognito JWT verification (minimal, Phase 1).

For production use, consider a battle-tested library like python-jose + JWKS
caching. This implementation validates a JWT against the Cognito JWKS endpoint
on cold start and caches keys in memory.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from functools import lru_cache
from typing import Any

from fastapi import Depends, Header, HTTPException, status

from ..config import get_settings

log = logging.getLogger("slideforge.auth")


@lru_cache(maxsize=1)
def _jwks() -> dict[str, Any]:
    s = get_settings()
    if not s.cognito_user_pool_id:
        return {"keys": []}
    url = (
        f"https://cognito-idp.{s.aws_region}.amazonaws.com/"
        f"{s.cognito_user_pool_id}/.well-known/jwks.json"
    )
    # Convert network failures into a 503 instead of a bare uncaught
    # URLError/timeout. Otherwise a NAT hiccup between the Lambda and
    # the Cognito IdP endpoint surfaces to the browser as a cryptic 500
    # with no body. lru_cache only caches successful returns, so a
    # transient failure will be re-attempted on the next request.
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"cannot reach Cognito JWKS: {e}",
        ) from e


def verify_token(token: str) -> dict[str, Any]:
    s = get_settings()
    if s.env == "local":
        # ENV=local bypass — return claims that satisfy every downstream
        # check, including the external API's scope requirement, so tests
        # can hit any endpoint without minting a real JWT.
        return {
            "sub": "local-user",
            "tenant_id": "local-tenant",
            "cognito:groups": ["admin"],
            "scope": s.external_api_required_scope or "slideforge-api/slides:create",
        }

    from jose import jwt  # local import keeps unit tests lightweight

    try:
        headers = jwt.get_unverified_header(token)
    except Exception as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token header") from e
    key = next((k for k in _jwks()["keys"] if k["kid"] == headers.get("kid")), None)
    if not key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown signing key")
    try:
        # Cognito ID tokens carry `aud = client_id`; access tokens don't have
        # `aud` but do carry `client_id`. Skip the library's audience check
        # and validate client_id manually below so both token types work.
        claims = jwt.decode(
            token,
            key,
            algorithms=[key["alg"]],
            options={"verify_aud": False},
        )
    except Exception as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"token invalid: {e}") from e

    if claims.get("token_use") not in ("access", "id"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unexpected token_use")

    expected_iss = f"https://cognito-idp.{s.aws_region}.amazonaws.com/{s.cognito_user_pool_id}"
    if s.cognito_user_pool_id and claims.get("iss") != expected_iss:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "issuer mismatch")

    if s.cognito_client_id:
        token_client = claims.get("client_id") or claims.get("aud")
        # Accept either the web user-pool client or the M2M
        # client_credentials client. The two share the same user pool
        # (same JWKS / issuer) but identify different callers — the
        # external router additionally requires the `slides:create`
        # scope, so unprivileged M2M tokens still can't reach user-only
        # endpoints (they have no Cognito-default user scope).
        allowed_clients = {s.cognito_client_id}
        if s.cognito_m2m_client_id:
            allowed_clients.add(s.cognito_m2m_client_id)
        if token_client not in allowed_clients:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "client_id mismatch")

    return claims


def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    # ENV=local (tests, local uvicorn) bypasses Cognito entirely so the
    # suite can drive the API without minting JWTs.
    if get_settings().env == "local":
        return verify_token("")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    return verify_token(token)


def require_tenant(user: dict[str, Any] = Depends(current_user)) -> str:
    """Resolve the tenant for the authenticated user.

    Phase 1 is an internal tool with 50 shared users collaborating on the
    same corpus of templates and projects. Until we add custom Cognito
    attributes + a tenant admin flow, everyone without an explicit
    `custom:tenant_id` (or `tenant_id`) claim is bucketed into a single
    default tenant so they can see each other's work.
    """
    return user.get("custom:tenant_id") or user.get("tenant_id") or "default"


def current_user_id(user: dict[str, Any] = Depends(current_user)) -> str:
    """Cognito `sub` (immutable per-user UUID) for owner-scoped resources.

    Used by the projects router to filter the project list per user.
    Unlike `email`, `sub` never changes, so existing rows survive an
    email-address change.

    Cognito client_credentials access tokens carry a `sub` claim that
    equals `client_id`, so external integrations land in this branch
    naturally and projects they create get owned by the calling client.
    Falling back to `client_id` covers the edge case where `sub` is
    missing (some non-Cognito JWTs).
    """
    sub = user.get("sub") or user.get("client_id")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no user id in token")
    return sub


def require_scope(required_scope: str):
    """Build a FastAPI dependency that rejects tokens missing `required_scope`.

    Cognito access tokens (both user and client_credentials) carry a
    space-separated `scope` claim, e.g.
    "slideforge-api/slides:create aws.cognito.signin.user.admin". Used
    to gate the external integration router so only callers whose M2M
    client was issued the `slides:create` scope can create projects via
    POST /api/v1/external/slides.

    Skipped entirely when the required_scope setting is empty (local
    dev / pytest with the scope check turned off).
    """

    def _dep(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if not required_scope:
            return user
        scope_claim = user.get("scope") or ""
        # Cognito serializes scopes space-separated. ID tokens don't
        # carry `scope` — only access tokens do — so a caller using an
        # ID token will be rejected here, which is the desired behavior
        # for an API meant for service-to-service traffic.
        scopes = scope_claim.split() if isinstance(scope_claim, str) else list(scope_claim)
        if required_scope not in scopes:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"missing required scope: {required_scope}",
            )
        return user

    return _dep


def require_admin(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    """Restrict an endpoint to members of the Cognito `admin` group.

    Currently used by template-deletion to keep destructive ops in the
    hands of designated admins (e.g. tsasaki@dx-design.co.jp). Add users
    to the group via Cognito console / CLI: aws cognito-idp
    admin-add-user-to-group --group-name admin ...
    """
    groups = user.get("cognito:groups") or []
    if "admin" not in groups:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin access required")
    return user
