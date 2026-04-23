"""Blueprint builder: LLM call + validation + retry."""

from __future__ import annotations

import logging
import os
from difflib import SequenceMatcher
from typing import Any, get_args

from pydantic import ValidationError

from ..models.schemas import FigureType, LayoutKind, SlideSpec
from .llm import LLMClient, LLMTruncatedError, extract_json

log = logging.getLogger("slideforge.blueprint")

MAX_RETRIES = 2

_VALID_FIGURE_TYPES = set(get_args(FigureType))
_VALID_LAYOUTS = set(get_args(LayoutKind))

_HEADLINE_PLACEHOLDER = "[headline_message 未指定]"
_HEADLINE_TITLE_OVERLAP_THRESHOLD = 0.70


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
    - After the above, map flat content fields into `content["slots"]`
      per Phase 2 design §4.4 so slot-aware renderers have a uniform
      input (legacy flat fields are preserved alongside).
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

        # Slot-shaping pass (§4.4): additive, preserves flat fields.
        slides[i - 1] = _apply_slot_sanitize(s)
        _enforce_headline_message(slides[i - 1])
        _check_headline_not_title_restate(slides[i - 1])


# Keys that identify the figure-data payload for a given figure_type.
# Where the payload is spread across multiple top-level keys (swot,
# matrix_2x2, pull_quote, stat_callout, image_slot), we fall through
# to the generic whole-content path in _apply_slot_sanitize.
_FIGURE_DATA_KEY: dict[str, str | None] = {
    "table": "table",
    "cards_grid": "cards",
    "two_column": None,  # left/right spread — handled by whole-content path
    "timeline": "steps",
    "stat_callout": None,
    "bullet_list": None,  # items mapped via the bullet_list branch above
    "comparison": None,  # left/right spread — handled by whole-content path
    "swot": None,
    "matrix_2x2": None,
    "pyramid": "levels",
    "org_chart": "nodes",
    "kpi_dashboard": "metrics",
    "pull_quote": None,
    "icon_list": "items",
    "process_flow": "steps",
    "gantt": "tasks",
    "stack_bar": "series",
    "waterfall": "changes",
    "cost_breakdown": "items",
    "image_slot": None,
}

# Flat keys that must never be swept into the generic figure `data` blob.
_SLOT_RESERVED_KEYS = frozenset(
    {"title", "subtitle", "body", "body_main", "note", "footer", "slots"}
)


def _data_key_for_figure(figure_type: str) -> str | None:
    """Return the single content key holding a figure's data, or None
    when the figure spans multiple top-level keys (use whole-content)."""
    return _FIGURE_DATA_KEY.get(figure_type)


def _apply_slot_sanitize(slide: dict[str, Any]) -> dict[str, Any]:
    """Return a new slide dict with `content["slots"]` populated from
    flat LLM fields per Phase 2 design §4.4.

    Preserves legacy flat keys. If `content["slots"]` already exists,
    the slide is returned unchanged (LLM produced slot-shaped output).
    Wrong-typed flat fields are silently skipped per-field.
    """
    content = slide.get("content")
    if not isinstance(content, dict):
        return slide

    if isinstance(content.get("slots"), dict):
        return slide

    slots: dict[str, Any] = {}

    title = content.get("title")
    if isinstance(title, str):
        slots["title"] = {"text": title}

    subtitle = content.get("subtitle")
    if isinstance(subtitle, str):
        slots["subtitle"] = {"text": subtitle}

    ft = slide.get("figure_type")
    body_main_assigned = False
    if isinstance(ft, str) and ft in _VALID_FIGURE_TYPES:
        key = _data_key_for_figure(ft)
        if key is not None:
            data = content.get(key)
            if data is not None:
                slots["body_main"] = {"figure": ft, "data": data}
                body_main_assigned = True
        else:
            # Whole-content path: gather non-reserved keys as the data blob.
            data = {k: v for k, v in content.items() if k not in _SLOT_RESERVED_KEYS}
            if data:
                slots["body_main"] = {"figure": ft, "data": data}
                body_main_assigned = True

    if not body_main_assigned:
        body = content.get("body")
        if not isinstance(body, str):
            body = content.get("body_main")
        if isinstance(body, str):
            slots["body_main"] = {"text": body}
            body_main_assigned = True

    if not body_main_assigned:
        items = content.get("bullets")
        if not isinstance(items, list):
            items = content.get("items")
        if isinstance(items, list):
            slots["body_main"] = {"figure": "bullet_list", "data": {"items": items}}
            body_main_assigned = True

    footnote = content.get("note")
    if not isinstance(footnote, str):
        footnote = content.get("footer")
    if isinstance(footnote, str):
        slots["footnote"] = {"text": footnote}

    new_content = dict(content)
    new_content["slots"] = slots
    new_slide = dict(slide)
    new_slide["content"] = new_content
    return new_slide


def _enforce_headline_message(slide: dict[str, Any]) -> None:
    """Fill missing headline_message with a placeholder when the feature
    flag is on. Flag-gated so existing blueprints keep loading."""
    # WHY: flag-gated rollout per Phase 2 §5.5 — never hard-fail.
    if os.environ.get("FF_HEADLINE_REQUIRED") != "1":
        return
    if not isinstance(slide, dict):
        return
    value = slide.get("headline_message")
    if isinstance(value, str) and value.strip():
        return
    idx = slide.get("index")
    log.warning(
        "slide %s: headline_message missing/blank; inserting placeholder",
        idx,
    )
    slide["headline_message"] = _HEADLINE_PLACEHOLDER


def _check_headline_not_title_restate(slide: dict[str, Any]) -> None:
    """Warn when headline_message is ≥70% overlap with the slide title."""
    if not isinstance(slide, dict):
        return
    headline = slide.get("headline_message")
    if not isinstance(headline, str) or not headline.strip():
        return
    if headline == _HEADLINE_PLACEHOLDER:
        return
    content = slide.get("content")
    title: str | None = None
    if isinstance(content, dict):
        slots = content.get("slots")
        if isinstance(slots, dict):
            slot_title = slots.get("title")
            if isinstance(slot_title, dict):
                t = slot_title.get("text")
                if isinstance(t, str):
                    title = t
        if title is None:
            t = content.get("title")
            if isinstance(t, str):
                title = t
    if not title or not title.strip():
        return
    a = _normalize_for_overlap(headline)
    b = _normalize_for_overlap(title)
    if not a or not b:
        return
    ratio = SequenceMatcher(a=a, b=b).ratio()
    if ratio >= _HEADLINE_TITLE_OVERLAP_THRESHOLD:
        log.warning(
            "slide %s: headline_message restates title (overlap=%.2f)",
            slide.get("index"),
            ratio,
        )


def _normalize_for_overlap(s: str) -> str:
    return "".join(ch for ch in s.strip() if not ch.isspace())


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
