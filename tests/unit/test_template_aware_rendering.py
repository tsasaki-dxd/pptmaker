"""Page counter rewrite + body-rect detection — these handle the two
template shapes that survived prior strip/replace iterations:

  * "<a:t>NN / MM</a:t>" — page footer baked into the template.
  * The body-area decoration shape that templates without <p:ph> use
    to mark "draw figures here". Reading the rect off it lets the
    renderer position figures correctly without resorting to slide-
    size guesses.
"""

from __future__ import annotations

from render.layout_renderer import (
    _detect_body_rect,
    _replace_page_counter,
    _replace_section_number,
)


def test_page_counter_rewrites_to_actual_total() -> None:
    src = "<p:sld>...<a:t>04 / 06</a:t>...</p:sld>"
    out = _replace_page_counter(src, current=4, total=18)
    assert "<a:t>04 / 18</a:t>" in out
    assert "<a:t>04 / 06</a:t>" not in out


def test_page_counter_handles_multiple_occurrences() -> None:
    src = "<a:t>01 / 06</a:t><a:t>02 / 06</a:t>"
    out = _replace_page_counter(src, current=2, total=18)
    assert out == "<a:t>02 / 18</a:t><a:t>02 / 18</a:t>"


def test_page_counter_zero_pads_both_numbers() -> None:
    src = "<a:t>1 / 6</a:t>"
    out = _replace_page_counter(src, current=1, total=9)
    assert out == "<a:t>01 / 09</a:t>"


def test_page_counter_ignores_unrelated_text() -> None:
    src = "<a:t>本文 / 図解 / 表</a:t>"  # not a page counter
    assert _replace_page_counter(src, current=1, total=10) == src


def test_detect_body_rect_finds_largest_prompt_shape() -> None:
    # Two body prompt shapes; pick the larger one (the actual body area).
    src = (
        "<p:sld><p:cSld><p:spTree>"
        # Big body prompt — should win.
        '<p:sp><p:nvSpPr><p:cNvPr id="1" name="body"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="365760" y="1737360"/>'
        '<a:ext cx="8412480" cy="2834640"/></a:xfrm></p:spPr>'
        "<p:txBody><a:p><a:r><a:t>本文 ／ 図版 ／ 表をここに配置</a:t></a:r></a:p></p:txBody></p:sp>"
        # Small body label — should be skipped (matches BODY exact pattern, not body container).
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="bodyLabel"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="200000" cy="100000"/></a:xfrm></p:spPr>'
        "<p:txBody><a:p><a:r><a:t>BODY</a:t></a:r></a:p></p:txBody></p:sp>"
        "</p:spTree></p:cSld></p:sld>"
    )
    rect = _detect_body_rect(src)
    assert rect == (365760, 1737360, 8412480, 2834640)


def test_section_number_preserves_double_space_separator() -> None:
    # Template convention is "SECTION<2 spaces>01"; after replacement
    # the spacing should stay the same so kerning stays aligned with
    # the surrounding chapter-ribbon typography.
    src = "<a:t>SECTION  01</a:t>"
    assert _replace_section_number(src, 2) == "<a:t>SECTION  02</a:t>"


def test_section_number_single_space_also_handled() -> None:
    src = "<a:t>SECTION 03</a:t>"
    assert _replace_section_number(src, 7) == "<a:t>SECTION 07</a:t>"


def test_section_number_lowercase_keyword_preserved() -> None:
    src = "<a:t>Section  01</a:t>"
    assert _replace_section_number(src, 4) == "<a:t>Section  04</a:t>"


def test_section_number_ignores_unrelated_text() -> None:
    src = "<a:t>本文 / 図解</a:t><a:t>このSECTIONは重要</a:t>"
    # Only the exact "SECTION <digits>" pattern at <a:t> boundary is
    # rewritten; prose containing SECTION stays untouched.
    assert _replace_section_number(src, 5) == src


def test_detect_body_rect_returns_none_when_no_prompt() -> None:
    src = (
        "<p:sld><p:cSld><p:spTree>"
        '<p:sp><p:nvSpPr><p:cNvPr id="1" name="x"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></a:xfrm></p:spPr>'
        "<p:txBody><a:p><a:r><a:t>普通の本文</a:t></a:r></a:p></p:txBody></p:sp>"
        "</p:spTree></p:cSld></p:sld>"
    )
    assert _detect_body_rect(src) is None
