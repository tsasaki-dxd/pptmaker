from __future__ import annotations

from render.qa.overflow import (
    Rect,
    check_grid_alignment,
    check_shape_collisions,
    check_slot_bounds,
    estimate_text_overflow,
)

SLIDE_WIDTH_EMU = 12192000
GRID_UNIT = SLIDE_WIDTH_EMU // 12  # 1016000


def test_shape_fully_inside_slot_returns_empty() -> None:
    slot = Rect(x=0, y=0, w=1000, h=1000)
    shape = Rect(x=100, y=100, w=500, h=500)
    assert check_slot_bounds("s1", shape, slot) == []


def test_right_overrun_by_100() -> None:
    slot = Rect(x=0, y=0, w=1000, h=1000)
    shape = Rect(x=0, y=0, w=1100, h=500)
    violations = check_slot_bounds("s1", shape, slot)
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == "slot_overflow"
    assert v.severity == "fail"
    assert v.shape_id == "s1"
    assert "right" in v.detail
    assert "100" in v.detail


def test_left_underrun_and_bottom_overrun_emit_two_violations() -> None:
    slot = Rect(x=100, y=0, w=1000, h=1000)
    shape = Rect(x=50, y=0, w=500, h=1100)
    violations = check_slot_bounds("s1", shape, slot)
    assert len(violations) == 2
    kinds = {v.detail.split()[0] for v in violations}
    assert "bottom" in kinds
    assert "left" in kinds
    for v in violations:
        assert v.kind == "slot_overflow"
        assert v.severity == "fail"


def test_tolerance_absorbs_small_overrun() -> None:
    slot = Rect(x=0, y=0, w=1000, h=1000)
    shape = Rect(x=0, y=0, w=1050, h=500)
    assert check_slot_bounds("s1", shape, slot, tolerance_emu=100) == []


def test_non_overlapping_shapes_no_collision() -> None:
    shapes = [
        ("a", Rect(x=0, y=0, w=100, h=100)),
        ("b", Rect(x=200, y=0, w=100, h=100)),
    ]
    assert check_shape_collisions(shapes) == []


def test_shared_edge_is_not_a_collision() -> None:
    shapes = [
        ("a", Rect(x=0, y=0, w=100, h=100)),
        ("b", Rect(x=100, y=0, w=100, h=100)),
    ]
    assert check_shape_collisions(shapes) == []


def test_two_shapes_overlapping_50x50() -> None:
    shapes = [
        ("a", Rect(x=0, y=0, w=100, h=100)),
        ("b", Rect(x=50, y=50, w=100, h=100)),
    ]
    violations = check_shape_collisions(shapes)
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == "shape_collision"
    assert v.severity == "fail"
    assert v.shape_id == "a"
    assert "b" in v.detail


def test_three_shapes_two_collisions() -> None:
    shapes = [
        ("A", Rect(x=0, y=0, w=100, h=100)),
        ("B", Rect(x=50, y=50, w=100, h=100)),
        ("C", Rect(x=10, y=10, w=20, h=20)),
    ]
    violations = check_shape_collisions(shapes)
    assert len(violations) == 2
    details = {v.detail for v in violations}
    assert "collides with B" in details
    assert "collides with C" in details
    assert all(v.shape_id == "A" for v in violations)


def test_fixed_rects_are_ignored() -> None:
    shapes = [("a", Rect(x=0, y=0, w=100, h=100))]
    fixed = [Rect(x=50, y=50, w=100, h=100)]
    assert check_shape_collisions(shapes, fixed=fixed) == []


def test_grid_aligned_shape_no_violation() -> None:
    shape = Rect(x=GRID_UNIT * 3, y=0, w=GRID_UNIT * 6, h=500)
    assert check_grid_alignment("s1", shape, SLIDE_WIDTH_EMU) == []


def test_x_off_grid_emits_warn() -> None:
    # tolerance = 10% of grid_unit = 101600
    shape = Rect(x=GRID_UNIT * 3 + 200000, y=0, w=GRID_UNIT * 6, h=500)
    violations = check_grid_alignment("s1", shape, SLIDE_WIDTH_EMU)
    # x is off; right edge happens to also be off by the same amount.
    assert len(violations) >= 1
    v = violations[0]
    assert v.kind == "grid_alignment"
    assert v.severity == "warn"
    assert "x off-grid" in v.detail


def test_x_on_grid_right_edge_off_grid() -> None:
    # width chosen so x is on-grid but right edge lands off-grid beyond tolerance.
    shape = Rect(x=GRID_UNIT * 2, y=0, w=GRID_UNIT * 3 + 200000, h=500)
    violations = check_grid_alignment("s1", shape, SLIDE_WIDTH_EMU)
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == "grid_alignment"
    assert v.severity == "warn"
    assert "right edge" in v.detail


def test_small_offset_within_default_tolerance() -> None:
    # off by 5% of grid_unit -> within default 10% tolerance
    offset = int(GRID_UNIT * 0.05)
    shape = Rect(x=GRID_UNIT * 2 + offset, y=0, w=GRID_UNIT * 4, h=500)
    assert check_grid_alignment("s1", shape, SLIDE_WIDTH_EMU) == []


def test_short_text_fits_returns_empty() -> None:
    frame = Rect(x=0, y=0, w=3_000_000, h=500_000)
    assert estimate_text_overflow("t1", "Hello", frame, font_size_pt=18.0) == []


def test_long_japanese_text_overflows() -> None:
    frame = Rect(x=0, y=0, w=2_000_000, h=500_000)
    text = "あ" * 200
    violations = estimate_text_overflow("t1", text, frame, font_size_pt=18.0)
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == "text_overflow"
    assert v.severity == "warn"
    assert v.shape_id == "t1"
    assert "frame.h 500000" in v.detail


def test_mixed_en_ja_width_sanity() -> None:
    fits_frame = Rect(x=0, y=0, w=4_000_000, h=500_000)
    assert estimate_text_overflow("t1", "Hello 世界", fits_frame, font_size_pt=18.0) == []

    overflow_frame = Rect(x=0, y=0, w=2_000_000, h=500_000)
    long_mixed = ("Hello 世界 " * 40).strip()
    violations = estimate_text_overflow("t2", long_mixed, overflow_frame, font_size_pt=18.0)
    assert len(violations) == 1
    assert violations[0].kind == "text_overflow"


def test_explicit_newlines_force_overflow() -> None:
    frame = Rect(x=0, y=0, w=5_000_000, h=500_000)
    text = "Hello\nWorld\nAgain"
    violations = estimate_text_overflow("t1", text, frame, font_size_pt=18.0)
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == "text_overflow"
    assert v.severity == "warn"
    assert "3 lines" in v.detail


def test_empty_string_returns_empty() -> None:
    frame = Rect(x=0, y=0, w=1_000_000, h=1_000_000)
    assert estimate_text_overflow("t1", "", frame, font_size_pt=18.0) == []
