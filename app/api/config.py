"""Runtime configuration pulled from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    env: str
    aws_region: str
    s3_bucket: str
    db_url: str
    render_queue_url: str
    cognito_user_pool_id: str
    cognito_client_id: str
    claude_model_blueprint: str
    claude_model_revision: str
    claude_model_brush: str
    anthropic_api_key_secret: str
    log_level: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        env=os.environ.get("ENV", "dev"),
        aws_region=os.environ.get("AWS_REGION", "ap-northeast-1"),
        s3_bucket=os.environ.get("S3_BUCKET", "slideforge-local"),
        db_url=os.environ.get("DB_URL", "sqlite:///./slideforge-local.db"),
        render_queue_url=os.environ.get("RENDER_QUEUE_URL", ""),
        cognito_user_pool_id=os.environ.get("COGNITO_USER_POOL_ID", ""),
        cognito_client_id=os.environ.get("COGNITO_CLIENT_ID", ""),
        claude_model_blueprint=os.environ.get("CLAUDE_MODEL_BLUEPRINT", "claude-sonnet-4-6"),
        claude_model_revision=os.environ.get("CLAUDE_MODEL_REVISION", "claude-sonnet-4-6"),
        claude_model_brush=os.environ.get("CLAUDE_MODEL_BRUSH", "claude-haiku-4-5-20251001"),
        anthropic_api_key_secret=os.environ.get("ANTHROPIC_API_KEY_SECRET", "slideforge/anthropic"),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
