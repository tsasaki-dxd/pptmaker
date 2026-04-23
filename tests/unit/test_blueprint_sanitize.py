"""Sanitization of LLM blueprint output before pydantic validation."""

from __future__ import annotations

import pytest

from api.services.blueprint_builder import _sanitize, _validate


def test_sanitize_coerces_invalid_figure_type() -> None:
    obj = {
        "title": "t",
        "slides": [
            {"index": 1, "layout": "content", "figure_type": "process_flow", "content": {"title": "x"}},
        ],
    }
    _sanitize(obj)
    assert obj["slides"][0]["figure_type"] is None
    _validate(obj)  # should pass now


def test_sanitize_coerces_invalid_layout() -> None:
    obj = {
        "title": "t",
        "slides": [
            {"index": 1, "layout": "executive_summary", "content": {}},
        ],
    }
    _sanitize(obj)
    assert obj["slides"][0]["layout"] == "content"
    _validate(obj)


def test_sanitize_fills_missing_index() -> None:
    obj = {
        "title": "t",
        "slides": [
            {"layout": "cover", "content": {}},
            {"layout": "content", "content": {}},
        ],
    }
    _sanitize(obj)
    assert [s["index"] for s in obj["slides"]] == [1, 2]
    _validate(obj)


def test_sanitize_preserves_valid_values() -> None:
    obj = {
        "title": "t",
        "slides": [
            {"index": 1, "layout": "content", "figure_type": "bullet_list", "content": {"items": ["a"]}},
        ],
    }
    _sanitize(obj)
    # Untouched
    assert obj["slides"][0]["figure_type"] == "bullet_list"
    assert obj["slides"][0]["layout"] == "content"
    _validate(obj)


def test_sanitize_coerces_non_dict_content() -> None:
    obj = {
        "title": "t",
        "slides": [{"index": 1, "layout": "content", "content": "oops not a dict"}],
    }
    _sanitize(obj)
    assert obj["slides"][0]["content"] == {}
    _validate(obj)


def test_sanitize_noop_on_malformed_root() -> None:
    # Root-level failures are caught by _validate, not _sanitize.
    _sanitize("not a dict")  # shouldn't raise
    _sanitize({"title": "t", "slides": "not a list"})  # shouldn't raise

    with pytest.raises(ValueError):
        _validate({"title": "t"})  # missing slides
