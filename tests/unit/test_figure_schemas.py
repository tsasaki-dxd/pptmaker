"""Tests for per-renderer input_schema_example declarations (Phase 2 §5.2)."""

from __future__ import annotations

import pytest

from render.figure_renderers import REGISTRY, list_capabilities, renderer_for


def test_every_renderer_has_figure_type_and_schema_dict() -> None:
    caps = list_capabilities()
    assert caps
    for cap in caps:
        ftype = cap["figure_type"]
        assert isinstance(ftype, str) and ftype, f"figure_type must be non-empty: {cap!r}"
        example = cap["input_schema_example"]
        assert isinstance(example, dict), (
            f"input_schema_example must be dict for {ftype}, got {type(example)!r}"
        )


def test_registry_instances_expose_input_schema_example() -> None:
    for ftype, inst in REGISTRY.items():
        assert hasattr(inst, "input_schema_example")
        assert isinstance(inst.input_schema_example, dict), ftype


@pytest.mark.parametrize(
    "figure_type",
    ["table", "cards_grid", "two_column", "timeline", "stat_callout"],
)
def test_example_passes_validation(figure_type: str) -> None:
    r = renderer_for(figure_type)
    example = r.input_schema_example
    assert example, f"{figure_type} example must be non-empty"
    result = r.validate(example)
    assert result.ok, f"{figure_type} example failed validation: {result.errors}"
