"""Blueprint builder: LLM call + validation + retry."""

from __future__ import annotations

import logging
from typing import Any, get_args

from pydantic import ValidationError

from ..models.schemas import FigureType, LayoutKind, SlideSpec
from .llm import LLMClient, LLMTruncatedError, extract_json

log = logging.getLogger("slideforge.blueprint")

MAX_RETRIES = 2

_VALID_FIGURE_TYPES = set(get_args(FigureType))
_VALID_LAYOUTS = set(get_args(LayoutKind))


class BlueprintBuildError(Exception):
    pass


def build_blueprint(
    *,
    llm: LLMClient,
    user_intent: str,
    required_sections: list[str],
    aux_context: str | None,
    template_summary: str,
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
            )
            parsed = extract_json(result.text)
            _sanitize(parsed)
            _validate(parsed)
            log.info("blueprint generated attempt=%d usage=%s", attempt, result.usage)
            return parsed
        except LLMTruncatedError as e:
            # Retrying won't help — max_tokens is the limit, a second
            # identical call will hit it again. Fail immediately.
            log.error("blueprint attempt=%d truncated: %s", attempt, e)
            raise BlueprintBuildError(str(e)) from e
        except Exception as e:
            log.warning("blueprint attempt=%d failed: %s", attempt, e)
            last_error = e
    raise BlueprintBuildError(f"exhausted retries: {last_error}")


def _sanitize(obj: Any) -> None:
    """Coerce LLM quirks in place so SlideSpec(**s) passes.

    The LLM reliably invents figure_types that aren't in FIGURE_CATALOG
    (e.g. 'process_flow', 'flowchart') and sometimes drops the
    per-slide `index`. Hard-failing and retrying wastes tokens because
    the next call produces the same output; coerce instead.

    - Unknown figure_type → None (slide renders with title only).
    - Unknown layout → 'content' (the safe default).
    - Missing/invalid index → assign by position.
    - content not dict → empty dict.
    """
    if not isinstance(obj, dict):
        return
    slides = obj.get("slides")
    if not isinstance(slides, list):
        return
    for i, s in enumerate(slides, start=1):
        if not isinstance(s, dict):
            continue
        idx = s.get("index")
        if not isinstance(idx, int) or idx < 1:
            s["index"] = i

        layout = s.get("layout")
        if layout not in _VALID_LAYOUTS:
            log.warning("slide %d: unknown layout=%r -> 'content'", s["index"], layout)
            s["layout"] = "content"

        ft = s.get("figure_type")
        if ft is not None and ft not in _VALID_FIGURE_TYPES:
            log.warning(
                "slide %d: unknown figure_type=%r -> None",
                s["index"],
                ft,
            )
            s["figure_type"] = None

        if not isinstance(s.get("content"), dict):
            s["content"] = {}


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
