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
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read())


def verify_token(token: str) -> dict[str, Any]:
    s = get_settings()
    if s.env == "local":
        return {"sub": "local-user", "tenant_id": "local-tenant", "cognito:groups": ["admin"]}

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
        if token_client != s.cognito_client_id:
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
