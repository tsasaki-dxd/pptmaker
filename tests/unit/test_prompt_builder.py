"""Tests for the dynamic blueprint system prompt builder (Phase 2 §5.3)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from api.prompts.builder import build_blueprint_system_prompt
from render.figure_renderers import list_capabilities


@pytest.fixture(autouse=True)
def _clear_builder_cache() -> Iterator[None]:
    # `build_blueprint_system_prompt` is `lru_cache`d. Clear before AND after
    # each test so that state from the process (or from a prior test) can't
    # leak in, and this test doesn't pollute the cache for later suites.
    build_blueprint_system_prompt.cache_clear()
    yield
    build_blueprint_system_prompt.cache_clear()


def test_contains_every_registered_figure_type() -> None:
    prompt = build_blueprint_system_prompt()
    caps = list_capabilities()
    assert caps, "registry must expose at least one renderer"
    for cap in caps:
        ftype = str(cap["figure_type"])
        assert f'"{ftype}"' in prompt, f"enum missing figure_type {ftype!r}"
        assert f"`{ftype}`" in prompt, f"skeleton line missing figure_type {ftype!r}"


def test_no_placeholders_remain_unsubstituted() -> None:
    prompt = build_blueprint_system_prompt()
    assert "{figure_type_enum}" not in prompt
    assert "{figure_type_skeletons}" not in prompt


def test_cache_clears_between_invocations() -> None:
    first = build_blueprint_system_prompt()
    info_before = build_blueprint_system_prompt.cache_info()
    assert info_before.currsize == 1
    build_blueprint_system_prompt.cache_clear()
    info_cleared = build_blueprint_system_prompt.cache_info()
    assert info_cleared.currsize == 0
    second = build_blueprint_system_prompt()
    # cache_clear worked: we recomputed, and the result is still correct.
    assert second == first


def test_output_byte_identical_across_invocations() -> None:
    a = build_blueprint_system_prompt()
    b = build_blueprint_system_prompt()
    assert a.encode("utf-8") == b.encode("utf-8")
