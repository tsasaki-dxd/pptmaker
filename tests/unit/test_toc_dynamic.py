"""Tests for dynamic TOC item handling — re-pitched / cloned to match
the blueprint's item count instead of being capped at the template's
prompt slot count."""

from __future__ import annotations

import re

from render.layout_renderer import _replace_toc_items


def _slot(idx: int, y: int, *, label: str = "項目タイトル", cy: int = 300_000) -> str:
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{idx}" name="toc{idx}"/>'
        f'<p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="2000000" y="{y}"/>'
        f'<a:ext cx="4000000" cy="{cy}"/></a:xfrm></p:spPr>'
        f'<p:txBody><a:p><a:r><a:t>{label}</a:t></a:r></a:p></p:txBody></p:sp>'
    )


def _slide_with_slots(count: int, *, pitch: int = 500_000) -> str:
    parts = ["<p:sld><p:cSld><p:spTree>"]
    for i in range(count):
        parts.append(_slot(i + 1, 1_000_000 + pitch * i))
    parts.append("</p:spTree></p:cSld></p:sld>")
    return "".join(parts)


def _texts(xml: str) -> list[str]:
    return re.findall(r"<a:t>([^<]*)</a:t>", xml)


def _ys(xml: str) -> list[int]:
    return [int(m.group(1)) for m in re.finditer(r'<a:off x="\d+" y="(\d+)"', xml)]


def _heights(xml: str) -> list[int]:
    return [int(m.group(1)) for m in re.finditer(r'<a:ext cx="\d+" cy="(\d+)"', xml)]


def test_n_equals_slot_count_keeps_original_positions() -> None:
    out = _replace_toc_items(_slide_with_slots(5), ["A", "B", "C", "D", "E"])
    assert _texts(out) == ["A", "B", "C", "D", "E"]
    assert _ys(out) == [1_000_000, 1_500_000, 2_000_000, 2_500_000, 3_000_000]


def test_extra_items_clone_with_compressed_pitch() -> None:
    # 6 items, 5 slots. Container range = (3.0M + 300k) - 1.0M = 2.3M.
    # Natural per item = 300k, gap = 200k. 6*300+5*200 = 2.8M > 2.3M.
    # Collapse gap to 0 → 6*300 = 1.8M ≤ 2.3M. Use natural_h, gap=0.
    out = _replace_toc_items(_slide_with_slots(5), ["A", "B", "C", "D", "E", "F"])
    assert _texts(out) == ["A", "B", "C", "D", "E", "F"]
    ys = _ys(out)
    assert len(ys) == 6
    # Pitch = item_h + gap = 300k + 0 = 300k.
    assert ys == [1_000_000 + 300_000 * i for i in range(6)]


def test_fewer_items_drop_trailing_slots() -> None:
    out = _replace_toc_items(_slide_with_slots(5), ["A", "B", "C"])
    assert _texts(out) == ["A", "B", "C"]
    # First 3 original positions preserved.
    assert _ys(out) == [1_000_000, 1_500_000, 2_000_000]


def test_heavy_overflow_shrinks_items_below_natural_height() -> None:
    # 10 items, 5 slots. After gap collapse still doesn't fit; item_h
    # gets distributed to 230k each, gap stays 0. 10*230k = 2.3M = container.
    out = _replace_toc_items(_slide_with_slots(5), [f"i{n}" for n in range(10)])
    assert _texts(out) == [f"i{n}" for n in range(10)]
    ys = _ys(out)
    heights = _heights(out)
    assert len(ys) == 10
    assert ys[0] == 1_000_000
    # Items must not extend past the original bottom (3.0M + 300k = 3.3M).
    assert ys[-1] + heights[-1] <= 3_300_000


def test_empty_items_returns_unchanged() -> None:
    src = _slide_with_slots(5)
    assert _replace_toc_items(src, []) == src


def test_no_template_slots_returns_unchanged() -> None:
    src = "<p:sld><p:cSld><p:spTree></p:spTree></p:cSld></p:sld>"
    assert _replace_toc_items(src, ["A", "B"]) == src


def test_textonly_fallback_when_no_xfrm() -> None:
    # Slot without <a:xfrm> — should still get text replaced.
    src = (
        "<p:sld><p:cSld><p:spTree>"
        '<p:sp><p:nvSpPr><p:cNvPr id="1" name="t"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        "<p:txBody><a:p><a:r><a:t>項目タイトル</a:t></a:r></a:p></p:txBody></p:sp>"
        "</p:spTree></p:cSld></p:sld>"
    )
    out = _replace_toc_items(src, ["A"])
    assert "A" in out
    assert "項目タイトル" not in out


def _entry_with_number(idx: int, y: int, num: str) -> str:
    """A TOC entry pair: number prefix shape + Japanese title shape.
    Number sits ~50k EMU above the anchor (mirrors the user's template
    where "01" is offset slightly from "項目タイトル" within the same
    visual band)."""
    number_y = y - 50_000
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{idx * 10}" name="num{idx}"/>'
        f'<p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="500000" y="{number_y}"/>'
        f'<a:ext cx="500000" cy="200000"/></a:xfrm></p:spPr>'
        f'<p:txBody><a:p><a:r><a:t>{num}</a:t></a:r></a:p></p:txBody></p:sp>'
    ) + _slot(idx, y)


def test_extras_clone_number_prefix_companion() -> None:
    # 5-entry template (pairs of number + 項目タイトル), expand to 6.
    parts = ["<p:sld><p:cSld><p:spTree>"]
    for i in range(5):
        parts.append(_entry_with_number(i + 1, 1_000_000 + 500_000 * i, f"{i + 1:02d}"))
    parts.append("</p:spTree></p:cSld></p:sld>")
    src = "".join(parts)

    out = _replace_toc_items(src, ["A", "B", "C", "D", "E", "F"])
    # All six titles present.
    for letter in "ABCDEF":
        assert f"<a:t>{letter}</a:t>" in out
    # All six number prefixes 01..06 present (the cloned 06 must exist).
    numbers = re.findall(r"<a:t>(0[1-9])</a:t>", out)
    assert numbers == ["01", "02", "03", "04", "05", "06"]


def test_fewer_items_drop_companion_numbers_too() -> None:
    parts = ["<p:sld><p:cSld><p:spTree>"]
    for i in range(5):
        parts.append(_entry_with_number(i + 1, 1_000_000 + 500_000 * i, f"{i + 1:02d}"))
    parts.append("</p:spTree></p:cSld></p:sld>")
    src = "".join(parts)

    out = _replace_toc_items(src, ["A", "B", "C"])
    # Only 01..03 should remain — 04 and 05 numbers dropped along with their titles.
    assert "<a:t>03</a:t>" in out
    assert "<a:t>04</a:t>" not in out
    assert "<a:t>05</a:t>" not in out
