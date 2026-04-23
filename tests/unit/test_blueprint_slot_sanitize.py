"""Flat-to-slot coercion in the blueprint sanitizer (Phase 2 §4.4)."""

from __future__ import annotations

from typing import Any

from api.services.blueprint_builder import (
    _apply_slot_sanitize,
    _data_key_for_figure,
    _sanitize,
)


def _slide(**kwargs: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"index": 1, "layout": "content", "content": {}}
    base.update(kwargs)
    return base


def test_flat_title_and_body_map_to_slots() -> None:
    slide = _slide(content={"title": "X", "body": "Y"})
    out = _apply_slot_sanitize(slide)
    slots = out["content"]["slots"]
    assert slots["title"] == {"text": "X"}
    assert slots["body_main"] == {"text": "Y"}
    # Flat fields preserved.
    assert out["content"]["title"] == "X"
    assert out["content"]["body"] == "Y"


def test_subtitle_and_footnote_mapping() -> None:
    slide = _slide(content={"title": "T", "subtitle": "S", "note": "N"})
    out = _apply_slot_sanitize(slide)
    slots = out["content"]["slots"]
    assert slots["subtitle"] == {"text": "S"}
    assert slots["footnote"] == {"text": "N"}


def test_footer_maps_to_footnote_when_note_absent() -> None:
    slide = _slide(content={"title": "T", "footer": "F"})
    out = _apply_slot_sanitize(slide)
    assert out["content"]["slots"]["footnote"] == {"text": "F"}


def test_figure_type_table_uses_single_data_key() -> None:
    slide = _slide(
        figure_type="table",
        content={
            "title": "X",
            "table": {"headers": ["a", "b"], "rows": [["1", "2"]]},
        },
    )
    out = _apply_slot_sanitize(slide)
    assert out["content"]["slots"]["body_main"] == {
        "figure": "table",
        "data": {"headers": ["a", "b"], "rows": [["1", "2"]]},
    }


def test_figure_type_cards_grid_uses_cards_key() -> None:
    slide = _slide(
        figure_type="cards_grid",
        content={"title": "X", "cards": [{"title": "c1"}, {"title": "c2"}]},
    )
    out = _apply_slot_sanitize(slide)
    assert out["content"]["slots"]["body_main"] == {
        "figure": "cards_grid",
        "data": [{"title": "c1"}, {"title": "c2"}],
    }


def test_figure_type_swot_uses_whole_content_path() -> None:
    slide = _slide(
        figure_type="swot",
        content={
            "title": "X",
            "strengths": {"items": ["s1"]},
            "weaknesses": {"items": ["w1"]},
            "opportunities": {"items": ["o1"]},
            "threats": {"items": ["t1"]},
        },
    )
    out = _apply_slot_sanitize(slide)
    assert out["content"]["slots"]["body_main"] == {
        "figure": "swot",
        "data": {
            "strengths": {"items": ["s1"]},
            "weaknesses": {"items": ["w1"]},
            "opportunities": {"items": ["o1"]},
            "threats": {"items": ["t1"]},
        },
    }


def test_no_figure_type_with_bullets_maps_to_bullet_list() -> None:
    slide = _slide(content={"title": "X", "bullets": ["a", "b", "c"]})
    out = _apply_slot_sanitize(slide)
    assert out["content"]["slots"]["body_main"] == {
        "figure": "bullet_list",
        "data": {"items": ["a", "b", "c"]},
    }


def test_no_figure_type_with_items_maps_to_bullet_list() -> None:
    slide = _slide(content={"title": "X", "items": ["a", "b"]})
    out = _apply_slot_sanitize(slide)
    assert out["content"]["slots"]["body_main"] == {
        "figure": "bullet_list",
        "data": {"items": ["a", "b"]},
    }


def test_existing_slots_are_preserved_identity() -> None:
    pre = {"title": {"text": "kept"}}
    slide = _slide(content={"title": "ignored", "slots": pre})
    out = _apply_slot_sanitize(slide)
    # Identity: no new dict wraps the existing slots.
    assert out is slide
    assert out["content"]["slots"] is pre


def test_non_string_title_is_skipped_without_raise() -> None:
    slide = _slide(content={"title": 123, "body": "ok"})
    out = _apply_slot_sanitize(slide)
    slots = out["content"]["slots"]
    assert "title" not in slots
    assert slots["body_main"] == {"text": "ok"}


def test_non_list_bullets_is_skipped_without_raise() -> None:
    slide = _slide(content={"title": "X", "bullets": "not-a-list"})
    out = _apply_slot_sanitize(slide)
    slots = out["content"]["slots"]
    assert "body_main" not in slots
    assert slots["title"] == {"text": "X"}


def test_figure_with_missing_data_key_omits_body_main_and_falls_back() -> None:
    # figure_type=table but no `table` key: body_main should be omitted
    # for the figure path; however body/bullets fallbacks may still kick in.
    slide = _slide(figure_type="table", content={"title": "X"})
    out = _apply_slot_sanitize(slide)
    slots = out["content"]["slots"]
    assert "body_main" not in slots


def test_integration_via_top_level_sanitize() -> None:
    obj = {
        "title": "t",
        "slides": [
            {
                "index": 1,
                "layout": "content",
                "figure_type": "table",
                "content": {
                    "title": "Hi",
                    "subtitle": "sub",
                    "table": {"headers": ["h"], "rows": [["r"]]},
                    "note": "fyi",
                },
            },
            {
                "index": 2,
                "layout": "content",
                "content": {"title": "Second", "bullets": ["x", "y"]},
            },
        ],
    }
    _sanitize(obj)
    s1 = obj["slides"][0]["content"]["slots"]
    assert s1["title"] == {"text": "Hi"}
    assert s1["subtitle"] == {"text": "sub"}
    assert s1["body_main"] == {
        "figure": "table",
        "data": {"headers": ["h"], "rows": [["r"]]},
    }
    assert s1["footnote"] == {"text": "fyi"}

    s2 = obj["slides"][1]["content"]["slots"]
    assert s2["title"] == {"text": "Second"}
    assert s2["body_main"] == {
        "figure": "bullet_list",
        "data": {"items": ["x", "y"]},
    }


def test_data_key_helper_known_mappings() -> None:
    assert _data_key_for_figure("table") == "table"
    assert _data_key_for_figure("cards_grid") == "cards"
    assert _data_key_for_figure("timeline") == "steps"
    assert _data_key_for_figure("pyramid") == "levels"
    assert _data_key_for_figure("kpi_dashboard") == "metrics"
    assert _data_key_for_figure("gantt") == "tasks"
    # Whole-content / spread cases return None.
    assert _data_key_for_figure("swot") is None
    assert _data_key_for_figure("matrix_2x2") is None
    assert _data_key_for_figure("pull_quote") is None
    assert _data_key_for_figure("image_slot") is None
