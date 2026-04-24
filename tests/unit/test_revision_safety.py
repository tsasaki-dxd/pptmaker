"""Revision handler path-whitelist tests."""

from __future__ import annotations

import pytest

from api.services.revision_handler import RevisionError, _check_patch_safety


def test_valid_patch_passes() -> None:
    patch = [
        {"op": "replace", "path": "/slides/0/content/title", "value": "T"},
        {"op": "add", "path": "/design_tokens/colors/primary", "value": "#8B7AB8"},
    ]
    _check_patch_safety(patch)


def test_disallowed_op_rejected() -> None:
    with pytest.raises(RevisionError):
        _check_patch_safety([{"op": "test", "path": "/slides/0"}])


def test_path_outside_tree_rejected() -> None:
    with pytest.raises(RevisionError):
        _check_patch_safety([{"op": "replace", "path": "/secret", "value": "x"}])


# ---- per-slide scope (slide_index != None) ----


def test_scoped_patch_within_slide_passes() -> None:
    patch = [
        {"op": "replace", "path": "/slides/4/content/title", "value": "T"},
        {"op": "replace", "path": "/slides/4/figure_type", "value": "table"},
        {"op": "replace", "path": "/slides/4/content", "value": {}},
        {"op": "replace", "path": "/slides/4", "value": {}},
    ]
    _check_patch_safety(patch, slide_index=5)  # 1-based -> index 4


def test_scoped_patch_touching_sibling_rejected() -> None:
    with pytest.raises(RevisionError, match="escapes slide_index"):
        _check_patch_safety(
            [{"op": "replace", "path": "/slides/3/content/title", "value": "x"}],
            slide_index=5,
        )


def test_scoped_patch_rejects_root_title_and_design_tokens() -> None:
    with pytest.raises(RevisionError, match="escapes slide_index"):
        _check_patch_safety(
            [{"op": "replace", "path": "/title", "value": "x"}],
            slide_index=5,
        )
    with pytest.raises(RevisionError, match="escapes slide_index"):
        _check_patch_safety(
            [{"op": "add", "path": "/design_tokens/x", "value": 1}],
            slide_index=5,
        )


def test_scoped_patch_prefix_trap_rejected() -> None:
    # "/slides/40" starts with "/slides/4" as a string but is a different
    # slide entirely — require either exact match or '/' boundary.
    with pytest.raises(RevisionError, match="escapes slide_index"):
        _check_patch_safety(
            [{"op": "replace", "path": "/slides/40/content", "value": {}}],
            slide_index=5,
        )
