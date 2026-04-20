"""Template layout classifier tests."""

from __future__ import annotations

from api.services.template_registry import _classify_slide


def test_first_slide_is_cover() -> None:
    layout, conf, _ = _classify_slide(1, "<x/>", total=10)
    assert layout == "cover"


def test_toc_detection_second_slide() -> None:
    layout, _, _ = _classify_slide(2, "<a:t>目次</a:t>", total=10)
    assert layout == "toc"


def test_disclaimer_detection_last_slide() -> None:
    layout, _, _ = _classify_slide(10, "<a:t>免責事項</a:t>", total=10)
    assert layout == "disclaimer"


def test_about_detection() -> None:
    layout, _, _ = _classify_slide(9, "<a:t>会社概要</a:t>", total=10)
    assert layout == "about"


def test_default_is_content() -> None:
    layout, _, _ = _classify_slide(5, "<a:t>メイン本文</a:t>", total=10)
    assert layout == "content"
