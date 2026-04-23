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


# --- title-replace coverage for the two other common markup shapes ---

CTR_TITLE_SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="1" name="Title"/><p:cNvSpPr><a:spLocks/></p:cNvSpPr>
<p:nvPr><p:ph type="ctrTitle"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>元タイトル</a:t></a:r></a:p></p:txBody>
</p:sp>
</p:spTree></p:cSld></p:sld>"""


IDX0_TITLE_SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="1" name="Title"/><p:cNvSpPr><a:spLocks/></p:cNvSpPr>
<p:nvPr><p:ph idx="0"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>元タイトル</a:t></a:r></a:p></p:txBody>
</p:sp>
</p:spTree></p:cSld></p:sld>"""


def test_title_replaced_ctr_title() -> None:
    req = RenderRequest(
        slide_index=1, layout="cover", figure_type=None, content={"title": "新タイトル"}
    )
    out = render_content_slide(CTR_TITLE_SLIDE, req)
    assert "新タイトル" in out
    assert "元タイトル" not in out


def test_title_replaced_idx0() -> None:
    req = RenderRequest(
        slide_index=1, layout="cover", figure_type=None, content={"title": "新タイトル"}
    )
    out = render_content_slide(IDX0_TITLE_SLIDE, req)
    assert "新タイトル" in out
    assert "元タイトル" not in out


# --- body placeholder stripping ---

SLIDE_WITH_BODY_PLACEHOLDER = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="1" name="Title"/><p:cNvSpPr/>
<p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:p><a:r><a:t>元タイトル</a:t></a:r></a:p></p:txBody>
</p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="2" name="Body"/><p:cNvSpPr/>
<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:p><a:r><a:t>本文をここに入れる</a:t></a:r></a:p></p:txBody>
</p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="3" name="Decoration"/><p:cNvSpPr/>
<p:nvPr/></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:p><a:r><a:t>CONTENT</a:t></a:r></a:p></p:txBody>
</p:sp>
</p:spTree></p:cSld></p:sld>"""


def test_body_placeholder_stripped_when_figure_renders() -> None:
    """Template body placeholder ("本文をここに入れる") must not leak
    through behind the injected figure shapes."""
    req = RenderRequest(
        slide_index=1,
        layout="content",
        figure_type="bullet_list",
        content={"title": "T", "items": ["a"]},
    )
    out = render_content_slide(SLIDE_WITH_BODY_PLACEHOLDER, req)
    assert "本文をここに入れる" not in out
    # Title placeholder survives (with its text replaced).
    assert "T</a:t>" in out
    # Non-placeholder decoration ("CONTENT" label, no <p:ph>) stays.
    assert "CONTENT" in out


def test_body_placeholder_kept_when_no_figure() -> None:
    """If the blueprint slide has no figure_type, we're only
    substituting text; leave the template alone otherwise."""
    req = RenderRequest(
        slide_index=1,
        layout="content",
        figure_type=None,
        content={"title": "新タイトル"},
    )
    out = render_content_slide(SLIDE_WITH_BODY_PLACEHOLDER, req)
    assert "本文をここに入れる" in out  # still there
    assert "新タイトル" in out
