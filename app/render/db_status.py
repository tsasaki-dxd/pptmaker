"""
Minimal DB write-back so the render Lambda can flip
ProjectRow.status when a job finishes.

Kept tiny on purpose — the render container doesn't share code with
the api/ package and we only need to UPDATE one column. Bringing in
SQLAlchemy + the full models module here would mean duplicating a lot
of unrelated schema.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Literal

log = logging.getLogger("slideforge.render.db_status")

ProjectStatus = Literal["complete", "partial", "failed"]


def update_project_status(project_id: str, status: ProjectStatus) -> None:
    """UPDATE projects SET status=... WHERE id=...

    No-op when DB env vars aren't configured (local invokes / unit
    tests). Logs but never raises — failure to update DB shouldn't
    blow up an otherwise-successful render job (the artifacts are
    already in S3).
    """
    secret_arn = os.environ.get("DB_SECRET_ARN")
    endpoint = os.environ.get("DB_ENDPOINT")
    if not (secret_arn and endpoint):
        log.warning(
            "DB_SECRET_ARN / DB_ENDPOINT not set; skipping status update for %s",
            project_id,
        )
        return

    try:
        import boto3

        sm = boto3.client(
            "secretsmanager",
            region_name=os.environ.get("AWS_REGION", "ap-northeast-1"),
        )
        secret = json.loads(sm.get_secret_value(SecretId=secret_arn)["SecretString"])

        import psycopg2

        conn = psycopg2.connect(
            host=endpoint,
            port=int(secret.get("port", 5432)),
            user=secret["username"],
            password=secret["password"],
            dbname=secret.get("dbname", "postgres"),
            connect_timeout=5,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE projects SET status = %s WHERE id = %s",
                    (status, project_id),
                )
                conn.commit()
                log.info("project %s status -> %s", project_id, status)
        finally:
            conn.close()
    except Exception:
        log.exception("failed to update project %s status to %s", project_id, status)
