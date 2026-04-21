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
