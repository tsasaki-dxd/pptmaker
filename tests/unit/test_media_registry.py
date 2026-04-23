"""Tests for MediaRegistry dedupe, rId stability, and slide_usages tracking."""

from __future__ import annotations

from render.media import ImageAssetDescriptor, MediaRegistry


def _desc(aid: str, mime: str = "image/png") -> ImageAssetDescriptor:
    return ImageAssetDescriptor(
        asset_id=aid, s3_key=f"assets/{aid}.png", mime=mime, width_px=800, height_px=600
    )


def test_register_assigns_stable_rid_from_10000() -> None:
    reg = MediaRegistry()
    rid = reg.register(_desc("a"), slide_index=1)
    assert rid == "rId10000"


def test_register_dedupes_same_asset_id() -> None:
    reg = MediaRegistry()
    d1 = _desc("a")
    d2 = _desc("a")
    rid1 = reg.register(d1, slide_index=1)
    rid2 = reg.register(d2, slide_index=2)
    assert rid1 == rid2 == "rId10000"
    assert len(reg.entries) == 1


def test_rid_stable_after_additional_registrations() -> None:
    reg = MediaRegistry()
    rid_a = reg.register(_desc("a"), slide_index=1)
    rid_b = reg.register(_desc("b"), slide_index=1)
    rid_c = reg.register(_desc("c"), slide_index=2)
    assert rid_a == "rId10000"
    assert rid_b == "rId10001"
    assert rid_c == "rId10002"

    rid_a_again = reg.register(_desc("a"), slide_index=3)
    assert rid_a_again == "rId10000"


def test_slide_usages_tracked() -> None:
    reg = MediaRegistry()
    reg.register(_desc("a"), slide_index=1)
    reg.register(_desc("b"), slide_index=1)
    reg.register(_desc("a"), slide_index=2)

    assert reg.slide_usages[1] == {"rId10000", "rId10001"}
    assert reg.slide_usages[2] == {"rId10000"}


def test_slide_usages_set_semantics_no_duplicates() -> None:
    reg = MediaRegistry()
    reg.register(_desc("a"), slide_index=5)
    reg.register(_desc("a"), slide_index=5)
    assert reg.slide_usages[5] == {"rId10000"}
