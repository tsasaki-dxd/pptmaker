"""Lazy slot migration for pre-existing TemplateProfile rows (Phase 2 §11)."""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from api.models.schemas import TemplateProfile
from api.services.template_registry import ensure_slots_populated

_SLIDE_OPEN = (
    '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    "<p:cSld><p:spTree>"
)
_SLIDE_CLOSE = "</p:spTree></p:cSld></p:sld>"


def _title_sp(xfrm: tuple[int, int, int, int]) -> str:
    x, y, cx, cy = xfrm
    return (
        "<p:sp><p:nvSpPr><p:cNvPr id='1' name='x'/><p:cNvSpPr/>"
        '<p:nvPr><p:ph type="title" idx="0"/></p:nvPr></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/>'
        f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm></p:spPr></p:sp>'
    )


def _slide_xml(*children: str) -> str:
    return _SLIDE_OPEN + "".join(children) + _SLIDE_CLOSE


def _build_pptx(slide_xmls: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, xml in enumerate(slide_xmls, start=1):
            zf.writestr(f"ppt/slides/slide{i}.xml", xml)
    return buf.getvalue()


def _make_profile(layouts: list[dict[str, Any]]) -> TemplateProfile:
    return TemplateProfile(
        id=uuid4(),
        tenant_id="t1",
        name="test",
        original_s3_path="s3://bucket/key.pptx",
        design_tokens={},
        layouts=layouts,
        template_slide_count=len(layouts),
        created_at=datetime.now(UTC),
    )


def test_v1_1_profile_returned_unchanged_no_fetcher_call() -> None:
    layouts = [
        {
            "index": 1,
            "layout": "cover",
            "confidence": 0.95,
            "reason": "first",
            "slots": [{"id": "title", "kind": "text", "rect": None, "role": "title", "idx": 0}],
            "fixed_elements": [],
        },
    ]
    profile = _make_profile(layouts)

    calls: list[str] = []

    def fetcher(uri: str) -> bytes | None:
        calls.append(uri)
        return None

    result = ensure_slots_populated(profile, fetcher)

    assert result is profile
    assert calls == []


def test_v1_0_profile_gets_slots_populated() -> None:
    slide1 = _slide_xml(_title_sp((100, 200, 300, 400)))
    slide2 = _slide_xml(_title_sp((1, 2, 3, 4)))
    body = _build_pptx([slide1, slide2])

    layouts = [
        {"index": 1, "layout": "cover", "confidence": 0.95, "reason": "r"},
        {"index": 2, "layout": "content", "confidence": 0.6, "reason": "r"},
    ]
    profile = _make_profile(layouts)

    def fetcher(_uri: str) -> bytes | None:
        return body

    result = ensure_slots_populated(profile, fetcher)

    assert result is not profile
    assert len(result.layouts) == 2
    for layout in result.layouts:
        assert "slots" in layout
        assert "fixed_elements" in layout

    assert len(result.layouts[0]["slots"]) == 1
    assert result.layouts[0]["slots"][0]["id"] == "title"
    # Flat rect format — layout_renderer reads slot["x"/"y"/"w"/"h"] directly.
    first = result.layouts[0]["slots"][0]
    assert (first["x"], first["y"], first["w"], first["h"]) == (100, 200, 300, 400)
    second = result.layouts[1]["slots"][0]
    assert (second["x"], second["y"], second["w"], second["h"]) == (1, 2, 3, 4)


def test_fetcher_none_returns_unchanged_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    layouts = [{"index": 1, "layout": "cover", "confidence": 0.95, "reason": "r"}]
    profile = _make_profile(layouts)

    def fetcher(_uri: str) -> bytes | None:
        return None

    with caplog.at_level(logging.WARNING, logger="slideforge.template"):
        result = ensure_slots_populated(profile, fetcher)

    assert result is profile
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("pptx_fetcher returned None" in r.getMessage() for r in warnings)


def test_malformed_pptx_bytes_returns_unchanged_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    layouts = [{"index": 1, "layout": "cover", "confidence": 0.95, "reason": "r"}]
    profile = _make_profile(layouts)

    def fetcher(_uri: str) -> bytes | None:
        return b"not a real pptx"

    with caplog.at_level(logging.WARNING, logger="slideforge.template"):
        result = ensure_slots_populated(profile, fetcher)

    assert result is profile
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("malformed pptx" in r.getMessage() for r in warnings)
