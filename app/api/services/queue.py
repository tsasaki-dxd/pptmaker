"""SQS submission for Render jobs."""

from __future__ import annotations

import json
import logging
from typing import Any

import boto3

from ..config import get_settings

log = logging.getLogger("slideforge.queue")


class RenderQueue:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.sqs = boto3.client("sqs", region_name=self.settings.aws_region)

    def submit(self, job: dict[str, Any]) -> str:
        if not self.settings.render_queue_url:
            log.warning("render queue URL not configured; job not submitted")
            return ""
        resp = self.sqs.send_message(
            QueueUrl=self.settings.render_queue_url,
            MessageBody=json.dumps(job, ensure_ascii=False),
        )
        return resp["MessageId"]
