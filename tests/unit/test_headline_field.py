"""Phase 2 scaffold tests for SlideSpec.headline_message."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.models.schemas import SlideSpec


def test_headline_message_defaults_to_none() -> None:
    s = SlideSpec(index=1, layout="content", content={})
    assert s.headline_message is None


def test_headline_message_valid_japanese_period() -> None:
    msg = "準委任契約により、5月1日以降は開発工数ベースで継続支援する。"
    s = SlideSpec(index=1, layout="content", content={}, headline_message=msg)
    assert s.headline_message == msg


def test_headline_message_valid_ascii_period() -> None:
    msg = "We will continue support based on effort after May 1."
    s = SlideSpec(index=1, layout="content", content={}, headline_message=msg)
    assert s.headline_message == msg


def test_headline_message_valid_fullwidth_exclamation() -> None:
    msg = "結論はこれです！"
    s = SlideSpec(index=1, layout="content", content={}, headline_message=msg)
    assert s.headline_message == msg


def test_headline_message_empty_string_rejected() -> None:
    with pytest.raises(ValidationError):
        SlideSpec(index=1, layout="content", content={}, headline_message="")


def test_headline_message_whitespace_only_rejected() -> None:
    with pytest.raises(ValidationError):
        SlideSpec(index=1, layout="content", content={}, headline_message="   ")


def test_headline_message_too_long_rejected() -> None:
    msg = "a" * 200 + "."  # 201 chars total
    with pytest.raises(ValidationError):
        SlideSpec(index=1, layout="content", content={}, headline_message=msg)


def test_headline_message_missing_punctuation_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        SlideSpec(index=1, layout="content", content={}, headline_message="結論はこれです")
    assert "sentence punctuation" in str(excinfo.value)


def test_headline_message_trims_whitespace() -> None:
    s = SlideSpec(
        index=1, layout="content", content={}, headline_message="  結論はこれです。  "
    )
    assert s.headline_message == "結論はこれです。"


def test_slide_spec_without_headline_message_field_backward_compat() -> None:
    # Omitting the field entirely must still build a valid SlideSpec.
    s = SlideSpec(index=1, layout="content", content={})
    assert s.headline_message is None
    assert s.index == 1
    assert s.layout == "content"
