"""Runtime configuration pulled from environment variables."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import quote_plus

log = logging.getLogger("slideforge.config")


@dataclass(frozen=True)
class Settings:
    env: str
    aws_region: str
    s3_bucket: str
    render_queue_url: str
    cognito_user_pool_id: str
    cognito_client_id: str
    claude_model_blueprint: str
    claude_model_revision: str
    claude_model_brush: str
    anthropic_api_key_secret: str
    log_level: str


_cached_db_url: str | None = None


def get_db_url() -> str:
    """Compose the SQLAlchemy DB URL. Lazy — only called on first DB access.

    Priority:
      1. DB_URL env var wins (local dev, explicit override).
      2. DB_SECRET_ARN + DB_ENDPOINT -> fetch the RDS credentials secret
         from Secrets Manager and build a postgres URL.
      3. Fallback to a local SQLite path (useful for unit tests).

    Deliberately kept OUT of `Settings` because a Secrets Manager call
    at Lambda cold-start import time (i.e. before the VPC ENI has
    stabilised / NAT route is ready) used to crash the whole module
    load, which then made even the OPTIONS preflight fail without CORS
    headers. Calling this lazily means OPTIONS can succeed before the
    DB link is ready.
    """
    global _cached_db_url
    if _cached_db_url is not None:
        return _cached_db_url

    override = os.environ.get("DB_URL")
    if override:
        _cached_db_url = override
        return override

    secret_arn = os.environ.get("DB_SECRET_ARN")
    endpoint = os.environ.get("DB_ENDPOINT")
    if secret_arn and endpoint:
        import boto3  # lazy import so unit tests without AWS still work

        sm = boto3.client(
            "secretsmanager",
            region_name=os.environ.get("AWS_REGION", "ap-northeast-1"),
        )
        value = sm.get_secret_value(SecretId=secret_arn)
        creds = json.loads(value["SecretString"])
        user = creds["username"]
        pwd = creds["password"]
        db_name = creds.get("dbname", "postgres")
        port = creds.get("port", 5432)
        _cached_db_url = (
            f"postgresql+psycopg2://{user}:{quote_plus(pwd)}"
            f"@{endpoint}:{port}/{db_name}"
        )
        return _cached_db_url

    _cached_db_url = "sqlite:///./slideforge-local.db"
    return _cached_db_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        env=os.environ.get("ENV", "dev"),
        aws_region=os.environ.get("AWS_REGION", "ap-northeast-1"),
        s3_bucket=os.environ.get("S3_BUCKET", "slideforge-local"),
        render_queue_url=os.environ.get("RENDER_QUEUE_URL", ""),
        cognito_user_pool_id=os.environ.get("COGNITO_USER_POOL_ID", ""),
        cognito_client_id=os.environ.get("COGNITO_CLIENT_ID", ""),
        claude_model_blueprint=os.environ.get("CLAUDE_MODEL_BLUEPRINT", "claude-sonnet-4-6"),
        claude_model_revision=os.environ.get("CLAUDE_MODEL_REVISION", "claude-sonnet-4-6"),
        claude_model_brush=os.environ.get("CLAUDE_MODEL_BRUSH", "claude-haiku-4-5-20251001"),
        anthropic_api_key_secret=os.environ.get("ANTHROPIC_API_KEY_SECRET", "slideforge/anthropic"),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )

