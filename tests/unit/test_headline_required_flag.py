"""Tests for FF_HEADLINE_REQUIRED flag-gated Pydantic enforcement."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.models.schemas import SlideSpec


def test_flag_off_allows_missing_headline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FF_HEADLINE_REQUIRED", raising=False)
    s = SlideSpec(index=1, layout="content", content={})
    assert s.headline_message is None


def test_flag_off_explicit_zero_allows_missing_headline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FF_HEADLINE_REQUIRED", "0")
    s = SlideSpec(index=1, layout="content", content={}, headline_message=None)
    assert s.headline_message is None


def test_flag_on_with_headline_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FF_HEADLINE_REQUIRED", "1")
    msg = "結論はこれです。"
    s = SlideSpec(index=1, layout="content", content={}, headline_message=msg)
    assert s.headline_message == msg


def test_flag_on_without_headline_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FF_HEADLINE_REQUIRED", "1")
    with pytest.raises(ValidationError) as excinfo:
        SlideSpec(index=1, layout="content", content={})
    assert "FF_HEADLINE_REQUIRED" in str(excinfo.value)


def test_flag_on_explicit_none_headline_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FF_HEADLINE_REQUIRED", "1")
    with pytest.raises(ValidationError) as excinfo:
        SlideSpec(index=1, layout="content", content={}, headline_message=None)
    assert "FF_HEADLINE_REQUIRED" in str(excinfo.value)


def test_flag_on_still_rejects_bad_format_at_field_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Field-level validator fires first: missing punctuation should fail there,
    # ensuring both layers (field_validator + model_validator) are active.
    monkeypatch.setenv("FF_HEADLINE_REQUIRED", "1")
    with pytest.raises(ValidationError) as excinfo:
        SlideSpec(index=1, layout="content", content={}, headline_message="no punct")
    assert "sentence punctuation" in str(excinfo.value)


def test_flag_on_blank_headline_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FF_HEADLINE_REQUIRED", "1")
    with pytest.raises(ValidationError):
        SlideSpec(index=1, layout="content", content={}, headline_message="   ")
