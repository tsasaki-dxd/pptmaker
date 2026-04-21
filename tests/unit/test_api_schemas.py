"""Pydantic schema validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.models.schemas import BlueprintCreate, SlideSpec


def test_slide_spec_accepts_valid() -> None:
    s = SlideSpec(index=1, layout="cover", content={"title": "T"})
    assert s.layout == "cover"


def test_slide_spec_rejects_bad_layout() -> None:
    with pytest.raises(ValidationError):
        SlideSpec(index=1, layout="bad", content={})


def test_slide_spec_requires_positive_index() -> None:
    with pytest.raises(ValidationError):
        SlideSpec(index=0, layout="cover", content={})


def test_blueprint_create_defaults() -> None:
    c = BlueprintCreate(intent="test")
    assert c.mode == "freeform"
    assert c.required_sections == []
