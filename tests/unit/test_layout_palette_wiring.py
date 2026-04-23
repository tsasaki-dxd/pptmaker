"""Palette theme-inheritance wiring tests (FF_THEME_INHERITANCE feature flag)."""

from __future__ import annotations

import io
import logging
import zipfile
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
from render.layout_renderer import RenderRequest, render_content_slide
from render.shapes import DEFAULT_PALETTE, Palette

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


def _theme_xml(accent1_hex: str = "FF0000") -> bytes:
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="t">'
        f"<a:themeElements>"
        f"<a:clrScheme name=\"s\">"
        f'<a:dk1><a:srgbClr val="3A3A42"/></a:dk1>'
        f'<a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
        f'<a:dk2><a:srgbClr val="5E5C6A"/></a:dk2>'
        f'<a:lt2><a:srgbClr val="E8E6EC"/></a:lt2>'
        f'<a:accent1><a:srgbClr val="{accent1_hex}"/></a:accent1>'
        f'<a:accent2><a:srgbClr val="C4A05C"/></a:accent2>'
        f'<a:accent3><a:srgbClr val="5E9B7F"/></a:accent3>'
        f'<a:accent4><a:srgbClr val="888888"/></a:accent4>'
        f'<a:accent5><a:srgbClr val="999999"/></a:accent5>'
        f'<a:accent6><a:srgbClr val="AAAAAA"/></a:accent6>'
        f'<a:hlink><a:srgbClr val="0000FF"/></a:hlink>'
        f'<a:folHlink><a:srgbClr val="551A8B"/></a:folHlink>'
        f"</a:clrScheme>"
        f'<a:fontScheme name="f">'
        f"<a:majorFont><a:latin typeface=\"Arial\"/><a:ea typeface=\"Meiryo\"/>"
        f"<a:cs typeface=\"\"/></a:majorFont>"
        f"<a:minorFont><a:latin typeface=\"Arial\"/><a:ea typeface=\"Meiryo\"/>"
        f"<a:cs typeface=\"\"/></a:minorFont>"
        f"</a:fontScheme>"
        f"<a:fmtScheme/>"
        f"</a:themeElements></a:theme>"
    ).encode()


def _theme_zip(accent1_hex: str = "FF0000") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ppt/theme/theme1.xml", _theme_xml(accent1_hex))
    return buf.getvalue()


class _CapturingRenderer(FigureRenderer):
    figure_type = "capture_palette"

    def __init__(self) -> None:
        self.seen_palette: Palette | None = None

    def validate(self, content: dict[str, Any]) -> ValidationResult:
        return ValidationResult(ok=True)

    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput:
        self.seen_palette = ctx.palette
        return RenderOutput(shapes_xml=[], next_shape_id=ctx.next_shape_id)


@pytest.fixture
def capturing_renderer(monkeypatch: pytest.MonkeyPatch) -> _CapturingRenderer:
    r = _CapturingRenderer()
    monkeypatch.setattr(layout_renderer, "renderer_for", lambda _t: r)
    return r


def _req() -> RenderRequest:
    return RenderRequest(
        slide_index=1,
        layout="content",
        figure_type="capture_palette",
        content={"title": "X"},
    )


def test_flag_off_default_palette(
    monkeypatch: pytest.MonkeyPatch, capturing_renderer: _CapturingRenderer
) -> None:
    monkeypatch.delenv("FF_THEME_INHERITANCE", raising=False)
    render_content_slide(BASE_SLIDE, _req(), theme_pptx_bytes=_theme_zip())
    assert capturing_renderer.seen_palette == DEFAULT_PALETTE


def test_flag_on_theme_drives_palette(
    monkeypatch: pytest.MonkeyPatch, capturing_renderer: _CapturingRenderer
) -> None:
    monkeypatch.setenv("FF_THEME_INHERITANCE", "1")
    render_content_slide(BASE_SLIDE, _req(), theme_pptx_bytes=_theme_zip("FF0000"))
    assert capturing_renderer.seen_palette is not None
    assert capturing_renderer.seen_palette.purple == "FF0000"


def test_flag_on_invalid_bytes_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capturing_renderer: _CapturingRenderer,
) -> None:
    monkeypatch.setenv("FF_THEME_INHERITANCE", "1")
    caplog.set_level(logging.WARNING, logger="render.layout_renderer")
    render_content_slide(BASE_SLIDE, _req(), theme_pptx_bytes=b"not a zip")
    assert capturing_renderer.seen_palette == DEFAULT_PALETTE
    assert any("theme load failed" in r.message for r in caplog.records)


def test_flag_on_no_bytes(
    monkeypatch: pytest.MonkeyPatch, capturing_renderer: _CapturingRenderer
) -> None:
    monkeypatch.setenv("FF_THEME_INHERITANCE", "1")
    render_content_slide(BASE_SLIDE, _req(), theme_pptx_bytes=None)
    assert capturing_renderer.seen_palette == DEFAULT_PALETTE


def test_flag_off_even_with_bytes(
    monkeypatch: pytest.MonkeyPatch, capturing_renderer: _CapturingRenderer
) -> None:
    monkeypatch.setenv("FF_THEME_INHERITANCE", "0")
    render_content_slide(BASE_SLIDE, _req(), theme_pptx_bytes=_theme_zip("00FF00"))
    assert capturing_renderer.seen_palette == DEFAULT_PALETTE
