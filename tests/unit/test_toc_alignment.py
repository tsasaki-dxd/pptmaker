"""TOC ↔ section_divider alignment in the blueprint builder.

The LLM regularly emits mismatched counts — 9 TOC items with only 5
section_divider slides, or the reverse. The renderer can't fix that
at render time; the fix belongs in the builder so the blueprint that
goes to review and render is always internally consistent.
"""

from __future__ import annotations

from typing import Any

from api.services.blueprint_builder import _align_toc_with_section_dividers


def test_truncates_toc_when_dividers_fewer() -> None:
    slides: list[Any] = [
        {"layout": "cover", "content": {}},
        {"layout": "toc", "content": {"items": [f"promised-{n}" for n in range(9)]}},
        {"layout": "section_divider", "content": {"title": "1. 課題認識"}},
        {"layout": "section_divider", "content": {"title": "2. 提案概要"}},
        {"layout": "section_divider", "content": {"title": "3. 推進体制"}},
    ]
    _align_toc_with_section_dividers(slides)
    assert slides[1]["content"]["items"] == ["1. 課題認識", "2. 提案概要", "3. 推進体制"]


def test_expands_toc_when_dividers_more() -> None:
    slides: list[Any] = [
        {"layout": "toc", "content": {"items": ["a"]}},
        *[
            {"layout": "section_divider", "content": {"title": f"sec{n}"}}
            for n in range(1, 6)
        ],
    ]
    _align_toc_with_section_dividers(slides)
    assert slides[0]["content"]["items"] == [f"sec{n}" for n in range(1, 6)]


def test_syncs_slots_items_when_present() -> None:
    slides: list[Any] = [
        {"layout": "toc", "content": {"items": ["old"], "slots": {"items": ["old"]}}},
        {"layout": "section_divider", "content": {"title": "sec1"}},
        {"layout": "section_divider", "content": {"title": "sec2"}},
    ]
    _align_toc_with_section_dividers(slides)
    assert slides[0]["content"]["items"] == ["sec1", "sec2"]
    assert slides[0]["content"]["slots"]["items"] == ["sec1", "sec2"]


def test_no_toc_is_noop() -> None:
    before: list[Any] = [
        {"layout": "content", "content": {}},
        {"layout": "section_divider", "content": {"title": "sec1"}},
    ]
    snapshot = [dict(s) for s in before]
    _align_toc_with_section_dividers(before)
    assert before == snapshot


def test_no_dividers_preserves_llm_toc() -> None:
    slides: list[Any] = [
        {"layout": "toc", "content": {"items": ["llm-authored"]}},
        {"layout": "content", "content": {}},
    ]
    _align_toc_with_section_dividers(slides)
    assert slides[0]["content"]["items"] == ["llm-authored"]


def test_strips_whitespace_from_divider_titles() -> None:
    slides: list[Any] = [
        {"layout": "toc", "content": {"items": []}},
        {"layout": "section_divider", "content": {"title": "  padded title  "}},
    ]
    _align_toc_with_section_dividers(slides)
    assert slides[0]["content"]["items"] == ["padded title"]


def test_ignores_dividers_with_missing_title() -> None:
    slides: list[Any] = [
        {"layout": "toc", "content": {"items": []}},
        {"layout": "section_divider", "content": {"title": "real"}},
        {"layout": "section_divider", "content": {}},
        {"layout": "section_divider", "content": {"title": ""}},
    ]
    _align_toc_with_section_dividers(slides)
    # Only the one with a real title is picked up.
    assert slides[0]["content"]["items"] == ["real"]


def test_first_toc_slide_wins_when_multiple() -> None:
    slides: list[Any] = [
        {"layout": "toc", "content": {"items": []}},
        {"layout": "section_divider", "content": {"title": "sec1"}},
        {"layout": "toc", "content": {"items": []}},  # ignored
    ]
    _align_toc_with_section_dividers(slides)
    assert slides[0]["content"]["items"] == ["sec1"]
    # Second toc stays empty; builder doesn't try to deduplicate.
    assert slides[2]["content"]["items"] == []
