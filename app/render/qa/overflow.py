from __future__ import annotations

import math
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

ViolationKind = Literal[
    "slot_overflow",
    "shape_collision",
    "grid_alignment",
    "text_overflow",
]
Severity = Literal["fail", "warn"]


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Violation:
    kind: ViolationKind
    shape_id: str
    detail: str
    severity: Severity


def check_slot_bounds(
    shape_id: str,
    shape: Rect,
    slot: Rect,
    *,
    tolerance_emu: int = 0,
) -> list[Violation]:
    violations: list[Violation] = []

    right_overrun = (shape.x + shape.w) - (slot.x + slot.w)
    if right_overrun > tolerance_emu:
        violations.append(
            Violation(
                kind="slot_overflow",
                shape_id=shape_id,
                detail=f"right overrun by {right_overrun} EMU",
                severity="fail",
            )
        )

    bottom_overrun = (shape.y + shape.h) - (slot.y + slot.h)
    if bottom_overrun > tolerance_emu:
        violations.append(
            Violation(
                kind="slot_overflow",
                shape_id=shape_id,
                detail=f"bottom overrun by {bottom_overrun} EMU",
                severity="fail",
            )
        )

    left_underrun = slot.x - shape.x
    if left_underrun > tolerance_emu:
        violations.append(
            Violation(
                kind="slot_overflow",
                shape_id=shape_id,
                detail=f"left underrun by {left_underrun} EMU",
                severity="fail",
            )
        )

    top_underrun = slot.y - shape.y
    if top_underrun > tolerance_emu:
        violations.append(
            Violation(
                kind="slot_overflow",
                shape_id=shape_id,
                detail=f"top underrun by {top_underrun} EMU",
                severity="fail",
            )
        )

    return violations


def check_shape_collisions(
    shapes: list[tuple[str, Rect]],
    fixed: Sequence[Rect] = (),
) -> list[Violation]:
    # `fixed` rects are ignored entirely per spec.
    _ = fixed
    violations: list[Violation] = []
    n = len(shapes)
    for i in range(n):
        id_a, rect_a = shapes[i]
        for j in range(i + 1, n):
            id_b, rect_b = shapes[j]
            if _intersects(rect_a, rect_b):
                violations.append(
                    Violation(
                        kind="shape_collision",
                        shape_id=id_a,
                        detail=f"collides with {id_b}",
                        severity="fail",
                    )
                )
    return violations


def check_grid_alignment(
    shape_id: str,
    shape: Rect,
    slide_width_emu: int,
    *,
    columns: int = 12,
    tolerance_ratio: float = 0.1,
) -> list[Violation]:
    grid_unit = slide_width_emu / columns
    tolerance = grid_unit * tolerance_ratio

    violations: list[Violation] = []

    left_off = _off_grid_distance(shape.x, grid_unit)
    if left_off > tolerance:
        violations.append(
            Violation(
                kind="grid_alignment",
                shape_id=shape_id,
                detail=f"x off-grid by {round(left_off)} EMU",
                severity="warn",
            )
        )

    right_edge = shape.x + shape.w
    right_off = _off_grid_distance(right_edge, grid_unit)
    if right_off > tolerance:
        violations.append(
            Violation(
                kind="grid_alignment",
                shape_id=shape_id,
                detail=f"right edge off-grid by {round(right_off)} EMU",
                severity="warn",
            )
        )

    return violations


def estimate_text_overflow(
    shape_id: str,
    text: str,
    frame: Rect,
    *,
    font_size_pt: float,
    line_height_ratio: float = 1.3,
    full_width_ratio: float = 1.0,
    half_width_ratio: float = 0.5,
) -> list[Violation]:
    if not text:
        return []

    full_count = sum(1 for c in text if unicodedata.east_asian_width(c) in ("F", "W", "A"))
    half_count = len(text) - full_count
    mix_ratio = (full_count * full_width_ratio + half_count * half_width_ratio) / len(text)

    avg = font_size_pt * 12700 * mix_ratio
    chars_per_line = max(1, int(frame.w // avg))

    segments = text.split("\n")
    total_lines = sum(max(1, math.ceil(len(seg) / chars_per_line)) for seg in segments)

    line_height_emu = int(font_size_pt * 12700 * line_height_ratio)

    if total_lines * line_height_emu > frame.h:
        return [
            Violation(
                kind="text_overflow",
                shape_id=shape_id,
                detail=(
                    f"estimated {total_lines} lines × {line_height_emu} EMU "
                    f"> frame.h {frame.h}"
                ),
                severity="warn",
            )
        ]
    return []


def _intersects(a: Rect, b: Rect) -> bool:
    # Strict overlap: shared edges (zero-area intersection) do NOT collide.
    if a.x + a.w <= b.x or b.x + b.w <= a.x:
        return False
    return not (a.y + a.h <= b.y or b.y + b.h <= a.y)


def _off_grid_distance(value: int, grid_unit: float) -> float:
    nearest = round(value / grid_unit) * grid_unit
    return abs(value - nearest)
