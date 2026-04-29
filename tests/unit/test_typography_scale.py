"""Tests for the typography scale tokens."""

from __future__ import annotations

import pytest

from render.typography import LINE_HEIGHT, TYPE_SCALE, pt


def test_scale_is_monotonically_increasing() -> None:
    # Scale tokens should be ordered smallest → largest so renderers
    # can reason about hierarchy.
    order = ["micro", "caption", "label", "body", "body_lg", "title", "h3", "h2", "h1", "display"]
    sizes = [TYPE_SCALE[k] for k in order]  # type: ignore[index]
    assert sizes == sorted(sizes), f"scale not monotonic: {sizes}"


def test_scale_reserved_for_strict_hierarchy() -> None:
    # Body / label / caption must each differ by at least 1 pt
    # so designers / renderers actually see a step in the hierarchy.
    assert TYPE_SCALE["body"] > TYPE_SCALE["label"]
    assert TYPE_SCALE["label"] > TYPE_SCALE["caption"]
    assert TYPE_SCALE["h2"] > TYPE_SCALE["title"]


def test_pt_resolver() -> None:
    assert pt("body") == 11
    assert pt("h2") == 24


def test_unknown_token_raises() -> None:
    with pytest.raises(KeyError):
        pt("oversized")  # type: ignore[arg-type]


def test_line_heights_present() -> None:
    assert LINE_HEIGHT["tight"] <= LINE_HEIGHT["normal"] <= LINE_HEIGHT["relaxed"]
