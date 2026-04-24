"""Revision handler: interpret natural-language instructions as JSON Patch."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import jsonpatch

if TYPE_CHECKING:
    from .llm import LLMClient

log = logging.getLogger("slideforge.revision")

ALLOWED_OPS = {"add", "remove", "replace", "move"}
ALLOWED_PATH_PREFIXES = ("/slides", "/design_tokens", "/title")


class RevisionError(Exception):
    pass


def apply_instruction(
    llm: LLMClient,
    current_blueprint: dict[str, Any],
    instruction: str,
    slide_index: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (patch, new_blueprint).

    When ``slide_index`` (1-based) is set, the LLM is instructed to only
    modify that one slide and every resulting patch op is required to
    target ``/slides/{slide_index-1}``. This lets the UI fire per-slide
    "rewrite this one" revisions without risking any bleed into sibling
    slides — giving back the determinism guarantee we'd otherwise need
    a partial renderer for.
    """
    from .llm import extract_json  # local import to avoid hard anthropic dep at import time

    result = llm.revision_patch(current_blueprint, instruction, slide_index=slide_index)
    patch = extract_json(result.text)
    if not isinstance(patch, list):
        raise RevisionError("patch must be a list")

    _check_patch_safety(patch, slide_index=slide_index)

    try:
        new = jsonpatch.apply_patch(current_blueprint, patch, in_place=False)
    except jsonpatch.JsonPatchException as e:
        raise RevisionError(f"patch application failed: {e}") from e

    log.info(
        "revision applied ops=%d slide_index=%s",
        len(patch),
        slide_index if slide_index is not None else "all",
    )
    return patch, new


def _check_patch_safety(
    patch: list[dict[str, Any]],
    slide_index: int | None = None,
) -> None:
    # When scoping, only /slides/{i} and its descendants are allowed
    # ("/slides/{i}" exact or "/slides/{i}/..." subtree). Anything else
    # — neighbour slides, /title, /design_tokens — is rejected.
    scope = f"/slides/{slide_index - 1}" if slide_index is not None else None

    for op in patch:
        if op.get("op") not in ALLOWED_OPS:
            raise RevisionError(f"disallowed op: {op.get('op')}")
        path = op.get("path", "")
        if scope is not None:
            if path != scope and not path.startswith(scope + "/"):
                raise RevisionError(
                    f"path {path!r} escapes slide_index={slide_index} scope"
                )
            continue
        if not any(path.startswith(p) for p in ALLOWED_PATH_PREFIXES):
            raise RevisionError(f"path outside allowed tree: {path}")
