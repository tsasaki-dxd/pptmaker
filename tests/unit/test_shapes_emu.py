"""Verify EMU integer guard in shape builders."""

from __future__ import annotations

import re

from render.shapes import inch, pill_label, rect_outline, rect_shape, text_box


def _assert_all_integer_emu(xml: str) -> None:
    for attr in ("x", "y", "cx", "cy"):
        for m in re.finditer(rf'{attr}="([^"]+)"', xml):
            val = m.group(1)
            assert val.lstrip("-").isdigit(), f"non-integer EMU in {attr}: {val!r}"


def test_rect_shape_integer_emu_with_float_inputs() -> None:
    x = inch(0.5) + 1 / 3
    y = inch(1.0) + 2 / 7
    w = inch(2.5) - 0.9
    h = inch(1.0) + 0.1
    xml = rect_shape(1, "r", x, y, w, h, "8B7AB8")
    _assert_all_integer_emu(xml)


def test_rect_outline_integer_emu() -> None:
    xml = rect_outline(2, "o", 1.5, 2.5, 3.5, 4.5, "6B5C96")
    _assert_all_integer_emu(xml)


def test_text_box_integer_emu() -> None:
    xml = text_box(3, "t", 1.1, 2.2, 3.3, 4.4, "hello", size_pt=12)
    _assert_all_integer_emu(xml)


def test_pill_label_integer_emu() -> None:
    xml = pill_label(4, "p", 1.5, 2.5, 800.9, 260.4, "Step 1", "8B7AB8")
    _assert_all_integer_emu(xml)


def test_inch_returns_integer() -> None:
    assert isinstance(inch(1.5), int)
    assert inch(1) == 914400


def test_xml_escape_on_title() -> None:
    xml = text_box(1, "x", 1.0, 1.0, 1.0, 1.0, "A & B <c>")
    assert "&amp;" in xml
    assert "&lt;" in xml
    assert "&gt;" in xml
