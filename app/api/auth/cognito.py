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
        claims = jwt.decode(
            token,
            key,
            algorithms=[key["alg"]],
            audience=s.cognito_client_id or None,
            options={"verify_aud": bool(s.cognito_client_id)},
        )
    except Exception as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"token invalid: {e}") from e
    return claims


def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    return verify_token(token)


def require_tenant(user: dict[str, Any] = Depends(current_user)) -> str:
    tenant = user.get("custom:tenant_id") or user.get("tenant_id")
    if not tenant:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "tenant not found in token")
    return tenant
