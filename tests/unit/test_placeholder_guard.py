from __future__ import annotations

import pytest

from render.qa.placeholder_guard import (
    DEFAULT_PLACEHOLDER_STRINGS,
    Leak,
    PlaceholderScanError,
    scan_placeholder_leak,
)

_SLIDE_OPEN = (
    '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
    ' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
    "<p:cSld><p:spTree>"
)
_SLIDE_CLOSE = "</p:spTree></p:cSld></p:sld>"


def _wrap_sp(shape_id: str, name: str, body_inner: str) -> str:
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{name}"/>'
        "<p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
        f"<p:spPr/><p:txBody><a:bodyPr/>{body_inner}</p:txBody></p:sp>"
    )


def _slide(*sps: str) -> str:
    return _SLIDE_OPEN + "".join(sps) + _SLIDE_CLOSE


def test_single_leak_resolves_shape_id() -> None:
    xml = _slide(
        _wrap_sp("5", "Body", "<a:p><a:r><a:t>本文をここに入れる</a:t></a:r></a:p>")
    )
    leaks = scan_placeholder_leak(xml)
    assert len(leaks) == 1
    leak = leaks[0]
    assert leak.offending_text == "本文をここに入れる"
    assert leak.shape_id == "5"
    assert leak.snippet == "本文をここに入れる"


def test_clean_slide_returns_empty() -> None:
    xml = _slide(
        _wrap_sp("1", "Title", "<a:p><a:r><a:t>ご依頼事項と契約形態</a:t></a:r></a:p>")
    )
    assert scan_placeholder_leak(xml) == []


def test_multi_run_split_concatenates_before_match() -> None:
    xml = _slide(
        _wrap_sp(
            "7",
            "Body",
            "<a:p><a:r><a:t>本文を</a:t></a:r><a:r><a:t>ここに入れる</a:t></a:r></a:p>",
        )
    )
    leaks = scan_placeholder_leak(xml)
    assert len(leaks) == 1
    assert leaks[0].offending_text == "本文をここに入れる"
    assert leaks[0].shape_id == "7"


def test_custom_needles_override_defaults() -> None:
    xml = _slide(
        _wrap_sp("2", "Body", "<a:p><a:r><a:t>本文をここに入れる XYZ</a:t></a:r></a:p>")
    )
    leaks = scan_placeholder_leak(xml, needles=("XYZ",))
    assert len(leaks) == 1
    assert leaks[0].offending_text == "XYZ"
    assert "本文をここに入れる" not in {leak.offending_text for leak in leaks}


def test_multiple_leaks_in_one_slide() -> None:
    xml = _slide(
        _wrap_sp("1", "Title", "<a:p><a:r><a:t>タイトルを入力</a:t></a:r></a:p>"),
        _wrap_sp("2", "Body", "<a:p><a:r><a:t>本文をここに入れる</a:t></a:r></a:p>"),
    )
    leaks = scan_placeholder_leak(xml)
    assert len(leaks) == 2
    ids = {leak.shape_id for leak in leaks}
    assert ids == {"1", "2"}


def test_malformed_xml_raises() -> None:
    with pytest.raises(PlaceholderScanError):
        scan_placeholder_leak("<p:sld><not closed")


def test_default_needles_exposed() -> None:
    assert "本文をここに入れる" in DEFAULT_PLACEHOLDER_STRINGS
    assert "Lorem ipsum" in DEFAULT_PLACEHOLDER_STRINGS


def test_leak_is_frozen_dataclass() -> None:
    leak = Leak(shape_id="1", offending_text="x", snippet="x")
    with pytest.raises(Exception):
        leak.shape_id = "2"  # type: ignore[misc]
