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
    llm: "LLMClient",
    current_blueprint: dict[str, Any],
    instruction: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (patch, new_blueprint)."""
    from .llm import extract_json  # local import to avoid hard anthropic dep at import time

    result = llm.revision_patch(current_blueprint, instruction)
    patch = extract_json(result.text)
    if not isinstance(patch, list):
        raise RevisionError("patch must be a list")

    _check_patch_safety(patch)

    try:
        new = jsonpatch.apply_patch(current_blueprint, patch, in_place=False)
    except jsonpatch.JsonPatchException as e:
        raise RevisionError(f"patch application failed: {e}") from e

    log.info("revision applied ops=%d", len(patch))
    return patch, new


def _check_patch_safety(patch: list[dict[str, Any]]) -> None:
    for op in patch:
        if op.get("op") not in ALLOWED_OPS:
            raise RevisionError(f"disallowed op: {op.get('op')}")
        path = op.get("path", "")
        if not any(path.startswith(p) for p in ALLOWED_PATH_PREFIXES):
            raise RevisionError(f"path outside allowed tree: {path}")
