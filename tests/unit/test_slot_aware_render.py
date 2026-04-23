"""Slot-aware rendering path tests (FF_SLOT_RENDER feature flag)."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from render import layout_renderer
from render.figure_renderers.base import (
    EMUBox,
    FigureRenderer,
    RenderContext,
    RenderOutput,
    ValidationResult,
)
from render.layout_renderer import (
    DEFAULT_BODY_AREA,
    RenderRequest,
    render_content_slide,
)

BASE_SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="1" name="Title"/><p:cNvSpPr><a:spLocks/></p:cNvSpPr>
<p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>T</a:t></a:r></a:p></p:txBody>
</p:sp>
</p:spTree></p:cSld>
</p:sld>"""


class _CapturingRenderer(FigureRenderer):
    figure_type = "capture"

    def __init__(self) -> None:
        self.seen_container: EMUBox | None = None

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        return ValidationResult(ok=True)

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        self.seen_container = container
        return RenderOutput(shapes_xml=["<p:sp/>"], next_shape_id=ctx.next_shape_id + 1)


@pytest.fixture
def capturing_renderer(monkeypatch: pytest.MonkeyPatch) -> _CapturingRenderer:
    cap = _CapturingRenderer()
    monkeypatch.setattr(layout_renderer, "renderer_for", lambda _t: cap)
    return cap


def _req() -> RenderRequest:
    return RenderRequest(
        slide_index=1,
        layout="content",
        figure_type="capture",
        content={"title": "T"},
    )


def test_flag_off_ignores_slots(
    monkeypatch: pytest.MonkeyPatch, capturing_renderer: _CapturingRenderer
) -> None:
    monkeypatch.delenv("FF_SLOT_RENDER", raising=False)
    slots = [{"kind": "figure", "x": 1, "y": 2, "w": 3, "h": 4}]
    render_content_slide(BASE_SLIDE, _req(), slots=slots)
    assert capturing_renderer.seen_container == DEFAULT_BODY_AREA


def test_flag_on_figure_slot_used(
    monkeypatch: pytest.MonkeyPatch, capturing_renderer: _CapturingRenderer
) -> None:
    monkeypatch.setenv("FF_SLOT_RENDER", "1")
    slot = {"kind": "figure", "x": 100, "y": 200, "w": 5000, "h": 3000}
    render_content_slide(BASE_SLIDE, _req(), slots=[slot])
    container = capturing_renderer.seen_container
    assert container is not None
    assert (container.x, container.y, container.w, container.h) == (100, 200, 5000, 3000)


def test_flag_on_no_figure_slot_falls_back_and_warns(
    monkeypatch: pytest.MonkeyPatch,
    capturing_renderer: _CapturingRenderer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("FF_SLOT_RENDER", "1")
    slots = [{"kind": "text", "x": 1, "y": 2, "w": 3, "h": 4}]
    with caplog.at_level(logging.WARNING, logger="render.layout_renderer"):
        render_content_slide(BASE_SLIDE, _req(), slots=slots)
    assert capturing_renderer.seen_container == DEFAULT_BODY_AREA
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)


def test_flag_on_largest_figure_slot_wins(
    monkeypatch: pytest.MonkeyPatch, capturing_renderer: _CapturingRenderer
) -> None:
    monkeypatch.setenv("FF_SLOT_RENDER", "1")
    small = {"kind": "figure", "x": 0, "y": 0, "w": 100, "h": 100}
    large = {"kind": "figure", "x": 10, "y": 20, "w": 4000, "h": 2000}
    render_content_slide(BASE_SLIDE, _req(), slots=[small, large])
    container = capturing_renderer.seen_container
    assert container is not None
    assert (container.x, container.y, container.w, container.h) == (10, 20, 4000, 2000)


def test_flag_on_empty_slots_falls_back_silently(
    monkeypatch: pytest.MonkeyPatch,
    capturing_renderer: _CapturingRenderer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("FF_SLOT_RENDER", "1")
    with caplog.at_level(logging.WARNING, logger="render.layout_renderer"):
        render_content_slide(BASE_SLIDE, _req(), slots=[])
    assert capturing_renderer.seen_container == DEFAULT_BODY_AREA
    assert not any(rec.levelno == logging.WARNING for rec in caplog.records)
