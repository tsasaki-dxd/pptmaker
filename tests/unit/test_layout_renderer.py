"""Layout renderer slide-XML assembly tests."""

from __future__ import annotations

from render.layout_renderer import RenderRequest, render_content_slide


BASE_SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="1" name="Title"/><p:cNvSpPr><a:spLocks/></p:cNvSpPr>
<p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>元タイトル</a:t></a:r></a:p></p:txBody>
</p:sp>
</p:spTree></p:cSld>
</p:sld>"""


def test_title_replaced() -> None:
    req = RenderRequest(
        slide_index=1,
        layout="content",
        figure_type=None,
        content={"title": "新タイトル"},
    )
    out = render_content_slide(BASE_SLIDE, req)
    assert "新タイトル" in out
    assert "元タイトル" not in out


def test_figure_shapes_injected() -> None:
    req = RenderRequest(
        slide_index=1,
        layout="content",
        figure_type="bullet_list",
        content={"title": "T", "items": ["a", "b"]},
    )
    out = render_content_slide(BASE_SLIDE, req)
    assert out.count("<p:sp>") > BASE_SLIDE.count("<p:sp>")


def test_invalid_content_raises() -> None:
    req = RenderRequest(
        slide_index=1,
        layout="content",
        figure_type="table",
        content={"title": "T", "headers": ["A"], "rows": []},
    )
    import pytest

    with pytest.raises(ValueError):
        render_content_slide(BASE_SLIDE, req)
