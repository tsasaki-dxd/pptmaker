"""Phase 2 end-to-end render integration test at the render_content_slide level.

Covers 受入基準 §10 #2, #3, #4, #5, #7 for a small blueprint/template pair with
all Phase 2 feature flags on. Handler-level E2E (SQS job, DB, preview) is out
of scope here — we drive the render function directly with a minimal template.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

import pytest

from render import layout_renderer
from render.figure_renderers.base import EMUBox
from render.layout_renderer import (
    DEFAULT_BODY_AREA,
    RenderRequest,
    default_body_area_for,
    render_content_slide,
)
from render.qa.placeholder_guard import (
    DEFAULT_PLACEHOLDER_STRINGS,
    scan_placeholder_leak,
)

_THEME_XML = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="t">'
    b"<a:themeElements>"
    b'<a:clrScheme name="s">'
    b'<a:dk1><a:srgbClr val="3A3A42"/></a:dk1>'
    b'<a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
    b'<a:dk2><a:srgbClr val="5E5C6A"/></a:dk2>'
    b'<a:lt2><a:srgbClr val="E8E6EC"/></a:lt2>'
    b'<a:accent1><a:srgbClr val="FF0000"/></a:accent1>'
    b'<a:accent2><a:srgbClr val="C4A05C"/></a:accent2>'
    b'<a:accent3><a:srgbClr val="5E9B7F"/></a:accent3>'
    b'<a:accent4><a:srgbClr val="888888"/></a:accent4>'
    b'<a:accent5><a:srgbClr val="999999"/></a:accent5>'
    b'<a:accent6><a:srgbClr val="AAAAAA"/></a:accent6>'
    b'<a:hlink><a:srgbClr val="0000FF"/></a:hlink>'
    b'<a:folHlink><a:srgbClr val="551A8B"/></a:folHlink>'
    b"</a:clrScheme>"
    b'<a:fontScheme name="f">'
    b'<a:majorFont><a:latin typeface="Arial"/><a:ea typeface="Meiryo"/>'
    b'<a:cs typeface=""/></a:majorFont>'
    b'<a:minorFont><a:latin typeface="Arial"/><a:ea typeface="Meiryo"/>'
    b'<a:cs typeface=""/></a:minorFont>'
    b"</a:fontScheme>"
    b"<a:fmtScheme/>"
    b"</a:themeElements></a:theme>"
)


def _theme_pptx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ppt/theme/theme1.xml", _THEME_XML)
    return buf.getvalue()


_CONTENT_SLIDE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="1" name="Title"/><p:cNvSpPr/>
<p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>
<a:p><a:r><a:t>クリックしてタイトルを入力</a:t></a:r></a:p></p:txBody>
</p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="2" name="Body"/><p:cNvSpPr/>
<p:nvPr><p:ph idx="1"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>
<a:p><a:r><a:t>本文をここに入れる</a:t></a:r></a:p></p:txBody>
</p:sp>
</p:spTree></p:cSld>
</p:sld>"""


def _body_slot(x: int, y: int, w: int, h: int) -> dict[str, Any]:
    return {"id": "body_main", "kind": "figure", "x": x, "y": y, "w": w, "h": h}


def _title_slot() -> dict[str, Any]:
    return {
        "id": "title",
        "kind": "text",
        "x": 457200,
        "y": 228600,
        "w": 11277600,
        "h": 685800,
    }


def _footer_slot() -> dict[str, Any]:
    return {
        "id": "footnote",
        "kind": "text",
        "x": 457200,
        "y": 6400800,
        "w": 11277600,
        "h": 228600,
    }


@pytest.fixture(autouse=True)
def _all_flags_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FF_SLOT_RENDER", "1")
    monkeypatch.setenv("FF_THEME_INHERITANCE", "1")


def test_theme_color_propagates_into_slide(monkeypatch: pytest.MonkeyPatch) -> None:
    slot_x, slot_y = 914400, 1524000
    slot_w, slot_h = 10287000, 4953000
    slots = [_title_slot(), _body_slot(slot_x, slot_y, slot_w, slot_h)]
    req = RenderRequest(
        slide_index=4,
        layout="content",
        figure_type="table",
        content={
            "title": "売上推移",
            "slots": {
                "title": {"text": "売上推移"},
                "body_main": {
                    "figure": "table",
                    "data": {
                        "headers": ["月", "売上"],
                        "rows": [["1 月", "100"], ["2 月", "120"]],
                    },
                },
            },
            "headers": ["月", "売上"],
            "rows": [["1 月", "100"], ["2 月", "120"]],
        },
    )
    out = render_content_slide(
        _CONTENT_SLIDE_XML,
        req,
        slots=slots,
        theme_pptx_bytes=_theme_pptx_bytes(),
    )
    assert "FF0000" in out


def test_no_placeholder_leak_under_slot_render() -> None:
    slots = [_title_slot(), _body_slot(914400, 1524000, 10287000, 4953000)]
    req = RenderRequest(
        slide_index=4,
        layout="content",
        figure_type="bullet_list",
        content={
            "title": "ポイント",
            "slots": {
                "title": {"text": "ポイント"},
                "body_main": {
                    "figure": "bullet_list",
                    "data": {"items": ["一つ目", "二つ目", "三つ目"]},
                },
            },
            "items": ["一つ目", "二つ目", "三つ目"],
        },
    )
    out = render_content_slide(_CONTENT_SLIDE_XML, req, slots=slots)
    leaks = scan_placeholder_leak(out, DEFAULT_PLACEHOLDER_STRINGS)
    assert leaks == []


def test_4_3_slide_size_reduces_body_area() -> None:
    captured: dict[str, EMUBox] = {}

    class _Capture:
        figure_type = "capture_43"

        def validate(self, c: dict[str, Any]) -> Any:
            from render.figure_renderers.base import ValidationResult
            return ValidationResult(ok=True)

        def render(self, c: dict[str, Any], container: EMUBox, ctx: Any) -> Any:
            from render.figure_renderers.base import RenderOutput
            captured["rect"] = container
            return RenderOutput(shapes_xml=[], next_shape_id=ctx.next_shape_id)

    instance = _Capture()
    layout_renderer.renderer_for = lambda _t: instance  # type: ignore[assignment]

    req = RenderRequest(
        slide_index=1,
        layout="content",
        figure_type="capture_43",
        content={"title": "X"},
    )
    render_content_slide(
        _CONTENT_SLIDE_XML,
        req,
        slide_size=(9144000, 6858000),
    )
    assert captured["rect"] != DEFAULT_BODY_AREA
    assert captured["rect"] == default_body_area_for((9144000, 6858000))


def test_slot_rect_used_over_default_body_area(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, EMUBox] = {}

    class _Capture:
        figure_type = "capture_slot"

        def validate(self, c: dict[str, Any]) -> Any:
            from render.figure_renderers.base import ValidationResult
            return ValidationResult(ok=True)

        def render(self, c: dict[str, Any], container: EMUBox, ctx: Any) -> Any:
            from render.figure_renderers.base import RenderOutput
            captured["rect"] = container
            return RenderOutput(shapes_xml=[], next_shape_id=ctx.next_shape_id)

    monkeypatch.setattr(layout_renderer, "renderer_for", lambda _t: _Capture())
    body = _body_slot(2000000, 2000000, 5000000, 3000000)
    req = RenderRequest(
        slide_index=1,
        layout="content",
        figure_type="capture_slot",
        content={"title": "X"},
    )
    render_content_slide(_CONTENT_SLIDE_XML, req, slots=[_title_slot(), body])
    assert captured["rect"] == EMUBox(2000000, 2000000, 5000000, 3000000)


def test_text_slots_render_visibly(monkeypatch: pytest.MonkeyPatch) -> None:
    slots = [_title_slot(), _footer_slot()]
    req = RenderRequest(
        slide_index=1,
        layout="content",
        figure_type=None,
        content={
            "title": "ヘッドライン",
            "slots": {
                "title": {"text": "ヘッドライン"},
                "footnote": {"text": "※ 注釈"},
            },
        },
    )
    out = render_content_slide(_CONTENT_SLIDE_XML, req, slots=slots)
    assert "※ 注釈" in out


def test_palette_fallback_when_theme_bytes_invalid(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    caplog.set_level(logging.WARNING, logger="render.layout_renderer")
    slots = [_title_slot(), _body_slot(914400, 1524000, 10287000, 4953000)]
    req = RenderRequest(
        slide_index=4,
        layout="content",
        figure_type="stat_callout",
        content={
            "title": "KPI",
            "slots": {
                "title": {"text": "KPI"},
                "body_main": {
                    "figure": "stat_callout",
                    "data": {"value": "42", "label": "単位", "note": "前期比"},
                },
            },
            "value": "42",
            "label": "単位",
            "note": "前期比",
        },
    )
    out = render_content_slide(
        _CONTENT_SLIDE_XML,
        req,
        theme_pptx_bytes=b"not a zip",
        slots=slots,
    )
    assert any("theme load failed" in r.message for r in caplog.records)
    # fallback path returned, slide still renders cleanly
    assert "<p:sld" in out and "</p:sld>" in out
    # theme's red did NOT leak in (fallback was used, not theme)
    assert "FF0000" not in out
