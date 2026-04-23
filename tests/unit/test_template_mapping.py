"""Default-mapping policy: blueprint slide layout should pick a
template page of the same layout type when available."""

from __future__ import annotations

from api.blueprint_worker import _assign_template_mapping


def _template(pages: list[tuple[int, str]]) -> list[dict]:
    return [{"index": i, "layout": layout} for i, layout in pages]


def test_cover_picks_cover_page() -> None:
    slides = [
        {"index": 1, "layout": "cover"},
        {"index": 2, "layout": "toc"},
    ]
    template_layouts = _template(
        [
            (1, "cover"),
            (2, "toc"),
            (3, "section_divider"),
            (4, "content"),
            (5, "content"),
            (6, "disclaimer"),
        ]
    )
    _assign_template_mapping(slides, template_layouts)
    assert slides[0]["template_slide_index"] == 1
    assert slides[1]["template_slide_index"] == 2


def test_content_cycles_among_content_pages() -> None:
    slides = [
        {"index": 1, "layout": "content"},
        {"index": 2, "layout": "content"},
        {"index": 3, "layout": "content"},
        {"index": 4, "layout": "content"},
    ]
    template_layouts = _template(
        [(1, "cover"), (2, "content"), (3, "content"), (4, "disclaimer")]
    )
    _assign_template_mapping(slides, template_layouts)
    # Four blueprint content slides cycle through the two template content pages.
    assert [s["template_slide_index"] for s in slides] == [2, 3, 2, 3]


def test_section_divider_reused_across_sections() -> None:
    slides = [
        {"index": 1, "layout": "section_divider"},
        {"index": 2, "layout": "section_divider"},
        {"index": 3, "layout": "section_divider"},
    ]
    template_layouts = _template([(1, "cover"), (2, "section_divider"), (3, "content")])
    _assign_template_mapping(slides, template_layouts)
    assert {s["template_slide_index"] for s in slides} == {2}


def test_missing_type_falls_back_to_content() -> None:
    slides = [{"index": 1, "layout": "about"}]
    template_layouts = _template([(1, "cover"), (2, "content")])
    _assign_template_mapping(slides, template_layouts)
    # No "about" page — falls back to the content bucket.
    assert slides[0]["template_slide_index"] == 2


def test_explicit_user_override_kept() -> None:
    slides = [{"index": 1, "layout": "content", "template_slide_index": 99}]
    template_layouts = _template([(1, "cover"), (2, "content")])
    _assign_template_mapping(slides, template_layouts)
    assert slides[0]["template_slide_index"] == 99  # respected as-is


def test_empty_template_noop() -> None:
    slides = [{"index": 1, "layout": "content"}]
    _assign_template_mapping(slides, [])
    # No classification info — leave it alone; render handler's cycling does the default.
    assert "template_slide_index" not in slides[0]
