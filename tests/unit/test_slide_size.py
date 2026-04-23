"""Slide-size extraction + dynamic body-area tests (Phase 2 §10 #4)."""

from __future__ import annotations

import io
import zipfile
from typing import Any

import pytest

from api.services import template_analyzer
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
    default_body_area_for,
    render_content_slide,
)
from render.shapes import inch

_PRES_OPEN = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:presentation '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
)
_PRES_CLOSE = "</p:presentation>"

_CX_16_9 = 12192000
_CY_16_9 = 6858000
_CX_4_3 = 9144000
_CY_4_3 = 6858000


def _pptx_with_presentation(pres_xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ppt/presentation.xml", pres_xml)
    return buf.getvalue()


def _sld_sz(cx: int, cy: int) -> str:
    return (
        _PRES_OPEN
        + f'<p:sldSz cx="{cx}" cy="{cy}" type="screen16x9"/>'
        + '<p:notesSz cx="6858000" cy="9144000"/>'
        + _PRES_CLOSE
    )


def test_extract_slide_size_16_9() -> None:
    body = _pptx_with_presentation(_sld_sz(_CX_16_9, _CY_16_9))
    assert template_analyzer._extract_slide_size(body) == (_CX_16_9, _CY_16_9)


def test_extract_slide_size_4_3() -> None:
    body = _pptx_with_presentation(_sld_sz(_CX_4_3, _CY_4_3))
    assert template_analyzer._extract_slide_size(body) == (_CX_4_3, _CY_4_3)


def test_extract_slide_size_missing_tag_returns_none() -> None:
    pres_xml = _PRES_OPEN + '<p:notesSz cx="6858000" cy="9144000"/>' + _PRES_CLOSE
    body = _pptx_with_presentation(pres_xml)
    assert template_analyzer._extract_slide_size(body) is None


def test_extract_slide_size_malformed_xml_returns_none() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ppt/presentation.xml", b"not really xml at all")
    assert template_analyzer._extract_slide_size(buf.getvalue()) is None


def test_extract_slide_size_missing_entry_returns_none() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ppt/slides/slide1.xml", b"<p:sld/>")
    assert template_analyzer._extract_slide_size(buf.getvalue()) is None


def test_extract_slide_size_not_a_zip_returns_none() -> None:
    assert template_analyzer._extract_slide_size(b"garbage bytes") is None


def test_extract_slide_size_missing_cx_cy_returns_none() -> None:
    pres_xml = _PRES_OPEN + "<p:sldSz/>" + _PRES_CLOSE
    body = _pptx_with_presentation(pres_xml)
    assert template_analyzer._extract_slide_size(body) is None


def test_default_body_area_for_16_9_matches_legacy() -> None:
    box = default_body_area_for((_CX_16_9, _CY_16_9))
    assert box == DEFAULT_BODY_AREA


def test_default_body_area_for_none_matches_legacy() -> None:
    assert default_body_area_for(None) == DEFAULT_BODY_AREA


def test_default_body_area_for_4_3_uses_adjusted_box() -> None:
    box = default_body_area_for((_CX_4_3, _CY_4_3))
    assert box.w <= _CX_4_3
    assert box.x + box.w <= _CX_4_3
    assert box.y + box.h <= _CY_4_3
    # 4:3 body area should be clearly narrower than the 16:9 one.
    assert box.w < DEFAULT_BODY_AREA.w
    # Expect around 9.2 inches wide.
    assert abs(box.w - inch(9.2)) <= inch(0.1)


def test_default_body_area_for_a4_portrait_scales_sensibly() -> None:
    cx, cy = 7560000, 10692000
    box = default_body_area_for((cx, cy))
    assert box.w <= cx
    assert box.h <= cy
    assert box.x + box.w <= cx
    assert box.y + box.h <= cy
    # Should scale proportionally from the 16:9 baseline.
    sx = cx / _CX_16_9
    sy = cy / _CY_16_9
    assert abs(box.w - int(DEFAULT_BODY_AREA.w * sx)) <= 2
    assert abs(box.h - int(DEFAULT_BODY_AREA.h * sy)) <= 2
    # Same margin ratio relative to cx as the 16:9 default.
    ratio_16_9 = DEFAULT_BODY_AREA.w / _CX_16_9
    ratio_a4 = box.w / cx
    assert abs(ratio_a4 - ratio_16_9) < 0.01


def test_default_body_area_for_zero_dims_falls_back() -> None:
    assert default_body_area_for((0, 0)) == DEFAULT_BODY_AREA


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


_BASE_SLIDE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
    "<p:cSld><p:spTree>"
    "<p:sp><p:nvSpPr><p:cNvPr id='1' name='Title'/><p:cNvSpPr/>"
    "<p:nvPr><p:ph type='title'/></p:nvPr></p:nvSpPr>"
    "<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>"
    "<a:p><a:r><a:t>T</a:t></a:r></a:p></p:txBody></p:sp>"
    "</p:spTree></p:cSld></p:sld>"
)


@pytest.fixture
def capturing_renderer(monkeypatch: pytest.MonkeyPatch) -> _CapturingRenderer:
    cap = _CapturingRenderer()
    monkeypatch.setattr(layout_renderer, "renderer_for", lambda _t: cap)
    return cap


def test_render_content_slide_4_3_slide_size_resizes_container(
    monkeypatch: pytest.MonkeyPatch, capturing_renderer: _CapturingRenderer
) -> None:
    monkeypatch.delenv("FF_SLOT_RENDER", raising=False)
    req = RenderRequest(
        slide_index=1,
        layout="content",
        figure_type="capture",
        content={"title": "T"},
    )
    render_content_slide(_BASE_SLIDE, req, slide_size=(_CX_4_3, _CY_4_3))
    container = capturing_renderer.seen_container
    assert container is not None
    expected = default_body_area_for((_CX_4_3, _CY_4_3))
    assert (container.x, container.y, container.w, container.h) == (
        expected.x,
        expected.y,
        expected.w,
        expected.h,
    )
    assert container.w < DEFAULT_BODY_AREA.w


def test_render_content_slide_16_9_slide_size_preserves_default(
    monkeypatch: pytest.MonkeyPatch, capturing_renderer: _CapturingRenderer
) -> None:
    monkeypatch.delenv("FF_SLOT_RENDER", raising=False)
    req = RenderRequest(
        slide_index=1,
        layout="content",
        figure_type="capture",
        content={"title": "T"},
    )
    render_content_slide(_BASE_SLIDE, req, slide_size=(_CX_16_9, _CY_16_9))
    assert capturing_renderer.seen_container == DEFAULT_BODY_AREA


def test_render_content_slide_none_slide_size_preserves_default(
    monkeypatch: pytest.MonkeyPatch, capturing_renderer: _CapturingRenderer
) -> None:
    monkeypatch.delenv("FF_SLOT_RENDER", raising=False)
    req = RenderRequest(
        slide_index=1,
        layout="content",
        figure_type="capture",
        content={"title": "T"},
    )
    render_content_slide(_BASE_SLIDE, req, slide_size=None)
    assert capturing_renderer.seen_container == DEFAULT_BODY_AREA


def test_render_content_slide_explicit_body_area_not_overridden(
    monkeypatch: pytest.MonkeyPatch, capturing_renderer: _CapturingRenderer
) -> None:
    monkeypatch.delenv("FF_SLOT_RENDER", raising=False)
    custom = EMUBox(x=1, y=2, w=3, h=4)
    req = RenderRequest(
        slide_index=1,
        layout="content",
        figure_type="capture",
        content={"title": "T"},
        body_area=custom,
    )
    render_content_slide(_BASE_SLIDE, req, slide_size=(_CX_4_3, _CY_4_3))
    assert capturing_renderer.seen_container == custom


def test_analyze_template_populates_slide_size_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ppt/presentation.xml", _sld_sz(_CX_4_3, _CY_4_3))
        zf.writestr(
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/'
            'presentationml/2006/main"><p:cSld><p:spTree/></p:cSld></p:sld>',
        )
    body = buf.getvalue()

    monkeypatch.setattr(template_analyzer, "_fetch_pptx", lambda _uri: body)
    monkeypatch.setattr(
        template_analyzer, "classify_layouts", lambda _p: []
    )

    result = template_analyzer.analyze_template("s3://bucket/k.pptx")
    assert result is not None
    assert result.design_tokens["slide_size"] == {
        "cx_emu": _CX_4_3,
        "cy_emu": _CY_4_3,
    }


def test_analyze_template_defaults_slide_size_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "ppt/presentation.xml",
            _PRES_OPEN + '<p:notesSz cx="1" cy="1"/>' + _PRES_CLOSE,
        )
        zf.writestr(
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/'
            'presentationml/2006/main"><p:cSld><p:spTree/></p:cSld></p:sld>',
        )
    body = buf.getvalue()

    monkeypatch.setattr(template_analyzer, "_fetch_pptx", lambda _uri: body)
    monkeypatch.setattr(
        template_analyzer, "classify_layouts", lambda _p: []
    )

    result = template_analyzer.analyze_template("s3://bucket/k.pptx")
    assert result is not None
    assert result.design_tokens["slide_size"] == {
        "cx_emu": _CX_16_9,
        "cy_emu": _CY_16_9,
    }
