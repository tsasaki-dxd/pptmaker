"""Template analyzer slot-extraction integration tests (Phase 2 §4.2)."""

from __future__ import annotations

import io
import logging
import zipfile

import pytest

from api.services import template_analyzer

_SLIDE_OPEN = (
    '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    "<p:cSld><p:spTree>"
)
_SLIDE_CLOSE = "</p:spTree></p:cSld></p:sld>"


def _sp(ph_type: str, idx: str, xfrm: tuple[int, int, int, int]) -> str:
    x, y, cx, cy = xfrm
    return (
        f"<p:sp><p:nvSpPr><p:cNvPr id='1' name='x'/><p:cNvSpPr/>"
        f'<p:nvPr><p:ph type="{ph_type}" idx="{idx}"/></p:nvPr></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/>'
        f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm></p:spPr></p:sp>'
    )


def _slide_xml(*children: str) -> str:
    return _SLIDE_OPEN + "".join(children) + _SLIDE_CLOSE


def _build_pptx(slide_xmls: list[str]) -> bytes:
    """Minimum .pptx-shaped zip containing N slides under ppt/slides/."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, xml in enumerate(slide_xmls, start=1):
            zf.writestr(f"ppt/slides/slide{i}.xml", xml)
    return buf.getvalue()


def test_happy_path_slots_attached_to_layouts(monkeypatch: pytest.MonkeyPatch) -> None:
    slide1 = _slide_xml(
        _sp("title", "0", (100, 200, 300, 400)),
        _sp("body", "1", (500, 600, 700, 800)),
    )
    slide2 = _slide_xml(_sp("title", "0", (1, 2, 3, 4)))
    body = _build_pptx([slide1, slide2])

    monkeypatch.setattr(template_analyzer, "_fetch_pptx", lambda _uri: body)

    result = template_analyzer.analyze_template("s3://bucket/key.pptx")

    assert result is not None
    assert result.slide_count == 2
    assert len(result.layouts) == 2

    layout1 = result.layouts[0]
    assert layout1["index"] == 1
    assert "slots" in layout1
    assert "fixed_elements" in layout1
    assert len(layout1["slots"]) == 2
    title_slot = layout1["slots"][0]
    # Must be plain dict, not a dataclass instance
    assert isinstance(title_slot, dict)
    assert title_slot["id"] == "title"
    assert title_slot["kind"] == "text"
    assert title_slot["role"] == "title"
    assert title_slot["idx"] == 0
    assert title_slot["rect"] == {"x": 100, "y": 200, "cx": 300, "cy": 400}

    body_slot = layout1["slots"][1]
    assert body_slot["id"] == "body_main"
    assert body_slot["role"] == "body"
    assert layout1["fixed_elements"] == []

    layout2 = result.layouts[1]
    assert layout2["index"] == 2
    assert len(layout2["slots"]) == 1
    assert layout2["slots"][0]["id"] == "title"


def test_malformed_slide_xml_yields_empty_slots_and_warns(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    good_slide = _slide_xml(_sp("title", "0", (1, 2, 3, 4)))
    malformed = "<p:sld><p:cSld><not-closed>"
    body = _build_pptx([good_slide, malformed])

    monkeypatch.setattr(template_analyzer, "_fetch_pptx", lambda _uri: body)

    with caplog.at_level(logging.WARNING, logger="slideforge.template_analyzer"):
        result = template_analyzer.analyze_template("s3://bucket/key.pptx")

    assert result is not None
    assert result.slide_count == 2
    assert len(result.layouts) == 2

    # Good slide still has its slots.
    assert len(result.layouts[0]["slots"]) == 1
    assert result.layouts[0]["slots"][0]["id"] == "title"

    # Malformed slide got empty lists, not an exception.
    assert result.layouts[1]["slots"] == []
    assert result.layouts[1]["fixed_elements"] == []

    # A warning was logged mentioning the slide.
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("slot extraction failed" in r.getMessage() for r in warnings)


def test_fetch_failure_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(template_analyzer, "_fetch_pptx", lambda _uri: None)
    assert template_analyzer.analyze_template("s3://bucket/missing.pptx") is None
