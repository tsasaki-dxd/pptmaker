"""Blueprint builder: LLM call + validation + retry."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from ..models.schemas import SlideSpec
from .llm import LLMClient, extract_json

log = logging.getLogger("slideforge.blueprint")

MAX_RETRIES = 2

# Figure-type catalog sent to the LLM. Lives here (not in the API
# router) because the blueprint worker needs it too and pulling it from
# a router module from a Lambda worker handler is backwards.
#
# IMPORTANT: keep these shape descriptions in sync with the actual
# `validate()` rules in app/render/figure_renderers/*. Drift here
# causes the render Lambda to reject LLM output and fail the whole job.
FIGURE_CATALOG = (
    "- table: 行×列の表、ヘッダ+交互背景。"
    "content: {title?, headers(2列以上), rows([[str]])}\n"
    "- cards_grid: 均等カード格子。content: {cards:[{title, body}], columns?}\n"
    "- two_column: 左右2カラム+任意フッタ。"
    "content: {left:{title, body?}, right:{title, body?}, footer?:{title, body?}}\n"
    "- timeline: 横タイムライン(2〜8ステップ)。"
    "content: {steps:[{label, body?}]}\n"
    "- stat_callout: 数値強調。content: {value, label, note?}\n"
    "- bullet_list: 箇条書き。content: {items:[...]}\n"
    "- comparison: 左右比較。content: {left:{title, items}, right:{title, items}}\n"
)


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
        except Exception as e:
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
