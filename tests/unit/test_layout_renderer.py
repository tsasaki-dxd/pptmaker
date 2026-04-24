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
    """Even with no figure, template placeholder prompt text must not
    leak through — it's filler, not content. The non-placeholder
    "CONTENT" decoration label stays."""
    req = RenderRequest(
        slide_index=1,
        layout="content",
        figure_type=None,
        content={"title": "新タイトル"},
    )
    out = render_content_slide(SLIDE_WITH_BODY_PLACEHOLDER, req)
    assert "本文をここに入れる" not in out
    assert "新タイトル" in out
    assert "CONTENT" in out


# Templates where prompt text sits in plain decoration text boxes
# (no <p:ph> marker). This pattern is common in Japanese corporate
# decks and was leaking through on every rendered slide before the
# prompt-pattern stripper was added.
SLIDE_WITH_DECORATION_PROMPTS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="1" name="t"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:p><a:r><a:t>コンテンツタイトル</a:t></a:r></a:p></p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="2" name="b"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:p><a:r><a:t>本文 / 図解 / 表をここに配置</a:t></a:r></a:p></p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="3" name="brand"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:p><a:r><a:t>DXデザインシステム株式会社</a:t></a:r></a:p></p:txBody></p:sp>
</p:spTree></p:cSld></p:sld>"""


def test_decoration_prompt_title_is_replaced_not_left() -> None:
    req = RenderRequest(
        slide_index=1,
        layout="content",
        figure_type=None,
        content={"title": "現状と理想のギャップ"},
    )
    out = render_content_slide(SLIDE_WITH_DECORATION_PROMPTS, req)
    assert "コンテンツタイトル" not in out
    assert "現状と理想のギャップ" in out
    assert "本文 / 図解 / 表をここに配置" not in out
    # Non-prompt decoration (brand name) stays.
    assert "DXデザインシステム株式会社" in out


def test_decoration_prompt_stripped_even_without_title() -> None:
    req = RenderRequest(
        slide_index=1,
        layout="section_divider",
        figure_type=None,
        content={},
    )
    out = render_content_slide(SLIDE_WITH_DECORATION_PROMPTS, req)
    # Both the title prompt and body prompt are filler; drop them.
    assert "コンテンツタイトル" not in out
    assert "本文 / 図解 / 表をここに配置" not in out
    assert "DXデザインシステム株式会社" in out


# Cover titles frequently span multiple styled <a:t> runs. Overwriting
# only the first run used to leave the tail visible (e.g. "タイトルを"
# got replaced but "ここに入れる。" stayed).
MULTI_RUN_TITLE_SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="1" name="Title"/><p:cNvSpPr/>
<p:nvPr><p:ph type="ctrTitle" idx="0"/></p:nvPr></p:nvSpPr>
<p:spPr/><p:txBody><a:bodyPr/><a:p>
<a:r><a:t>タイトルを</a:t></a:r><a:r><a:t>ここに入れる。</a:t></a:r>
</a:p></p:txBody></p:sp>
</p:spTree></p:cSld></p:sld>"""


def test_multi_run_title_fully_replaced() -> None:
    req = RenderRequest(
        slide_index=1,
        layout="cover",
        figure_type=None,
        content={"title": "DXコンサルティング提案書"},
    )
    out = render_content_slide(MULTI_RUN_TITLE_SLIDE, req)
    assert "DXコンサルティング提案書" in out
    assert "タイトルを" not in out
    assert "ここに入れる" not in out


TOC_SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="1" name="i1"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
<p:spPr/><p:txBody><a:p><a:r><a:t>項目タイトル</a:t></a:r></a:p></p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="2" name="i2"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
<p:spPr/><p:txBody><a:p><a:r><a:t>項目タイトル</a:t></a:r></a:p></p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="3" name="i3"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
<p:spPr/><p:txBody><a:p><a:r><a:t>項目タイトル</a:t></a:r></a:p></p:txBody></p:sp>
</p:spTree></p:cSld></p:sld>"""


def test_toc_items_populate_item_title_slots() -> None:
    req = RenderRequest(
        slide_index=2,
        layout="toc",
        figure_type=None,
        content={"items": ["課題認識", "提案概要", "推進体制"]},
    )
    out = render_content_slide(TOC_SLIDE, req)
    assert "課題認識" in out
    assert "提案概要" in out
    assert "推進体制" in out
    assert "項目タイトル" not in out


def test_toc_extra_slots_stripped_when_fewer_items() -> None:
    req = RenderRequest(
        slide_index=2,
        layout="toc",
        figure_type=None,
        content={"items": ["課題認識", "提案概要"]},
    )
    out = render_content_slide(TOC_SLIDE, req)
    assert "課題認識" in out and "提案概要" in out
    # The third "項目タイトル" slot has no item; the shape gets dropped.
    assert "項目タイトル" not in out
