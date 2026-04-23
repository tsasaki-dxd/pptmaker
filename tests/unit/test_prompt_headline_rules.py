"""Headline-message enforcement in prompt template + sanitizer (Phase 2 §5.5)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest

from api.prompts.builder import build_blueprint_system_prompt
from api.services.blueprint_builder import (
    _check_headline_not_title_restate,
    _enforce_headline_message,
)


@pytest.fixture(autouse=True)
def _clear_builder_cache() -> Iterator[None]:
    build_blueprint_system_prompt.cache_clear()
    yield
    build_blueprint_system_prompt.cache_clear()


@pytest.fixture
def _clear_ff_headline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FF_HEADLINE_REQUIRED", raising=False)


def test_prompt_contains_headline_rule_phrases() -> None:
    prompt = build_blueprint_system_prompt()
    assert "1 スライド 1 メッセージ" in prompt
    assert "headline_message" in prompt
    assert "SCR" in prompt
    assert "句点で終える" in prompt


def test_prompt_top_level_schema_lists_headline_message() -> None:
    prompt = build_blueprint_system_prompt()
    assert '"headline_message": string' in prompt


def test_enforcement_off_leaves_slide_unchanged(
    _clear_ff_headline: None, caplog: pytest.LogCaptureFixture
) -> None:
    slide: dict[str, Any] = {"index": 1, "layout": "content", "content": {}}
    with caplog.at_level(logging.WARNING, logger="slideforge.blueprint"):
        _enforce_headline_message(slide)
    assert "headline_message" not in slide
    assert not any("headline_message" in rec.message for rec in caplog.records)


def test_enforcement_on_fills_placeholder_and_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("FF_HEADLINE_REQUIRED", "1")
    slide: dict[str, Any] = {"index": 3, "layout": "content", "content": {}}
    with caplog.at_level(logging.WARNING, logger="slideforge.blueprint"):
        _enforce_headline_message(slide)
    assert slide["headline_message"] == "[headline_message 未指定]"
    assert any("headline_message missing" in rec.message for rec in caplog.records)


def test_enforcement_on_blank_string_filled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("FF_HEADLINE_REQUIRED", "1")
    slide: dict[str, Any] = {
        "index": 4,
        "layout": "content",
        "content": {},
        "headline_message": "   ",
    }
    with caplog.at_level(logging.WARNING, logger="slideforge.blueprint"):
        _enforce_headline_message(slide)
    assert slide["headline_message"] == "[headline_message 未指定]"


def test_enforcement_on_preserves_existing_headline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FF_HEADLINE_REQUIRED", "1")
    slide: dict[str, Any] = {
        "index": 2,
        "layout": "content",
        "content": {},
        "headline_message": "結論はこれです。",
    }
    _enforce_headline_message(slide)
    assert slide["headline_message"] == "結論はこれです。"


def test_title_restate_detection_warns_on_identical(
    caplog: pytest.LogCaptureFixture,
) -> None:
    slide: dict[str, Any] = {
        "index": 7,
        "layout": "content",
        "content": {"title": "市場は拡大している。"},
        "headline_message": "市場は拡大している。",
    }
    with caplog.at_level(logging.WARNING, logger="slideforge.blueprint"):
        _check_headline_not_title_restate(slide)
    assert any("restates title" in rec.message for rec in caplog.records)


def test_title_restate_detection_warns_on_slot_title(
    caplog: pytest.LogCaptureFixture,
) -> None:
    slide: dict[str, Any] = {
        "index": 8,
        "layout": "content",
        "content": {"slots": {"title": {"text": "価格戦略の刷新が必要。"}}},
        "headline_message": "価格戦略の刷新が必要。",
    }
    with caplog.at_level(logging.WARNING, logger="slideforge.blueprint"):
        _check_headline_not_title_restate(slide)
    assert any("restates title" in rec.message for rec in caplog.records)


def test_title_restate_detection_silent_when_different(
    caplog: pytest.LogCaptureFixture,
) -> None:
    slide: dict[str, Any] = {
        "index": 9,
        "layout": "content",
        "content": {"title": "市場環境"},
        "headline_message": "競合は縮小を続け、当社は今こそ投資すべきである。",
    }
    with caplog.at_level(logging.WARNING, logger="slideforge.blueprint"):
        _check_headline_not_title_restate(slide)
    assert not any("restates title" in rec.message for rec in caplog.records)


def test_title_restate_detection_silent_on_placeholder(
    caplog: pytest.LogCaptureFixture,
) -> None:
    slide: dict[str, Any] = {
        "index": 10,
        "layout": "content",
        "content": {"title": "[headline_message 未指定]"},
        "headline_message": "[headline_message 未指定]",
    }
    with caplog.at_level(logging.WARNING, logger="slideforge.blueprint"):
        _check_headline_not_title_restate(slide)
    assert not any("restates title" in rec.message for rec in caplog.records)
