"""Blueprint builder: LLM call + validation + retry."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from ..models.schemas import Blueprint, SlideSpec
from .llm import LLMClient, extract_json

log = logging.getLogger("slideforge.blueprint")

MAX_RETRIES = 2


class BlueprintBuildError(Exception):
    pass


def build_blueprint(
    *,
    llm: LLMClient,
    user_intent: str,
    required_sections: list[str],
    aux_context: str | None,
    template_summary: str,
    figure_catalog: str,
) -> dict[str, Any]:
    """Call the LLM and validate until we have a schema-compliant object."""
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = llm.blueprint(
                user_intent=user_intent,
                required_sections=required_sections,
                aux_context=aux_context,
                template_summary=template_summary,
                figure_catalog=figure_catalog,
            )
            parsed = extract_json(result.text)
            _validate(parsed)
            log.info("blueprint generated attempt=%d usage=%s", attempt, result.usage)
            return parsed
        except Exception as e:  # noqa: BLE001
            log.warning("blueprint attempt=%d failed: %s", attempt, e)
            last_error = e
    raise BlueprintBuildError(f"exhausted retries: {last_error}")


def _validate(obj: Any) -> None:
    if not isinstance(obj, dict):
        raise ValueError("root must be object")
    if "title" not in obj or "slides" not in obj:
        raise ValueError("title and slides required")
    try:
        for s in obj["slides"]:
            SlideSpec(**s)
    except ValidationError as e:
        raise ValueError(f"slide schema: {e}") from e
