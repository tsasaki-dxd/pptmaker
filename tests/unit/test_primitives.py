"""Tests for the new shape primitives that the LayoutSpec emitter
will use — multi-paragraph text, rounded rectangles with custom
radius, italic / underline runs, and palette-token color resolution.
"""

from __future__ import annotations

from render.shapes import (
    DEFAULT_PALETTE,
    TextParagraph,
    TextRun,
    resolve_palette_color,
    round_rect_shape,
    text_box,
    text_box_paragraphs,
)


def test_round_rect_emits_roundrect_geom() -> None:
    xml = round_rect_shape(1, "card", 0, 0, 1000, 500, "8B7AB8", corner_radius_pct=20)
    assert 'prst="roundRect"' in xml
    # 20% → 20000 in OOXML adj units.
    assert 'fmla="val 20000"' in xml


def test_round_rect_clamps_corner_radius() -> None:
    high = round_rect_shape(1, "x", 0, 0, 100, 100, "FFFFFF", corner_radius_pct=200)
    assert 'fmla="val 50000"' in high
    low = round_rect_shape(1, "x", 0, 0, 100, 100, "FFFFFF", corner_radius_pct=-5)
    assert 'fmla="val 0"' in low


def test_text_box_paragraphs_multiple_paragraphs() -> None:
    paras = [
        TextParagraph(runs=(TextRun(text="一行目", size_pt=12, bold=True),)),
        TextParagraph(runs=(TextRun(text="二行目", size_pt=10),)),
    ]
    xml = text_box_paragraphs(1, "x", 0, 0, 1000, 500, paras)
    # Two <a:p> blocks present.
    assert xml.count("<a:p>") == 2
    assert "一行目" in xml and "二行目" in xml


def test_text_box_paragraphs_bullet_char() -> None:
    paras = [
        TextParagraph(
            runs=(TextRun(text="ポイント1"),),
            bullet="•",
        ),
    ]
    xml = text_box_paragraphs(1, "x", 0, 0, 100, 100, paras)
    assert '<a:buChar char="•"/>' in xml
    # Hanging indent emitted.
    assert 'marL="285750"' in xml
    assert 'indent="-285750"' in xml


def test_text_box_paragraphs_auto_numbered_bullet() -> None:
    paras = [TextParagraph(runs=(TextRun(text="x"),), bullet="1.")]
    xml = text_box_paragraphs(1, "x", 0, 0, 100, 100, paras)
    assert '<a:buAutoNum type="arabicPeriod"/>' in xml


def test_text_box_paragraphs_anchor_and_line_spacing() -> None:
    paras = [
        TextParagraph(runs=(TextRun(text="x"),), line_spacing_pct=150)
    ]
    xml = text_box_paragraphs(1, "x", 0, 0, 100, 100, paras, anchor="ctr")
    assert 'anchor="ctr"' in xml
    assert '<a:lnSpc><a:spcPct val="150000"/></a:lnSpc>' in xml


def test_text_box_paragraphs_indent_level() -> None:
    paras = [TextParagraph(runs=(TextRun(text="x"),), indent_level=2)]
    xml = text_box_paragraphs(1, "x", 0, 0, 100, 100, paras)
    assert 'lvl="2"' in xml
    assert f'marL="{285750 * 2}"' in xml


def test_run_italic_underline_emit_attrs() -> None:
    paras = [
        TextParagraph(
            runs=(
                TextRun(text="斜め", italic=True),
                TextRun(text="下線", underline=True),
            ),
        )
    ]
    xml = text_box_paragraphs(1, "x", 0, 0, 100, 100, paras)
    assert ' i="1"' in xml
    assert ' u="sng"' in xml


def test_resolve_palette_color_passes_hex_through() -> None:
    assert resolve_palette_color("8b7ab8") == "8B7AB8"
    assert resolve_palette_color("#3A3A42") == "3A3A42"


def test_resolve_palette_color_resolves_token() -> None:
    assert resolve_palette_color("purple") == DEFAULT_PALETTE.purple
    assert resolve_palette_color("amber") == DEFAULT_PALETTE.amber
    # Unknown token falls back to purple, not a crash.
    assert resolve_palette_color("nonexistent") == DEFAULT_PALETTE.purple


def test_existing_text_box_unchanged() -> None:
    """Backward-compat: the old text_box signature still works for
    every existing figure renderer that hasn't been migrated."""
    xml = text_box(1, "x", 0, 0, 100, 100, "hi", size_pt=10)
    assert "<a:t>hi</a:t>" in xml
