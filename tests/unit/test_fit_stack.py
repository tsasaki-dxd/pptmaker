"""Tests for the fit_stack helper used by figure renderers to keep
N-item vertical stacks within their container height."""

from __future__ import annotations

from render.shapes import fit_stack


def test_zero_items_returns_zero() -> None:
    assert fit_stack(container_h=1_000_000, n=0, natural_h=100, min_h=50) == (0, 0)


def test_natural_fits_returns_natural() -> None:
    # 5 * 100k + 4 * 20k = 580k; container 1_000_000 → fits at natural.
    assert fit_stack(
        container_h=1_000_000,
        n=5,
        natural_h=100_000,
        min_h=40_000,
        gap=20_000,
        min_gap=5_000,
    ) == (100_000, 20_000)


def test_collapse_gap_first_when_overflow() -> None:
    # 5 * 200k + 4 * 50k = 1_200k; container 1_050_000.
    # With min_gap=10k: 5*200k + 4*10k = 1_040k → fits without touching height.
    assert fit_stack(
        container_h=1_050_000,
        n=5,
        natural_h=200_000,
        min_h=80_000,
        gap=50_000,
        min_gap=10_000,
    ) == (200_000, 10_000)


def test_shrink_item_h_when_gap_collapse_insufficient() -> None:
    # 8 items, natural 200k, gap 20k, min_gap 5k.
    # Natural total = 8*200k + 7*20k = 1_740k.
    # With min_gap: 8*200k + 7*5k = 1_635k.
    # container 800k.
    # Distribute: (800k - 7*5k) / 8 = 765k/8 = 95_625
    item_h, gap = fit_stack(
        container_h=800_000,
        n=8,
        natural_h=200_000,
        min_h=50_000,
        gap=20_000,
        min_gap=5_000,
    )
    assert gap == 5_000
    assert item_h == 95_625
    # Verify it actually fits.
    assert 8 * item_h + 7 * gap <= 800_000


def test_floors_at_min_h_when_too_many_items() -> None:
    # 20 items, min_h=80k → minimum stack = 20*80k = 1_600k. container 500k.
    # Should return (min_h, min_gap) and let caller handle.
    item_h, gap = fit_stack(
        container_h=500_000,
        n=20,
        natural_h=200_000,
        min_h=80_000,
        gap=10_000,
        min_gap=0,
    )
    assert item_h == 80_000
    assert gap == 0


def test_header_and_footer_reserved() -> None:
    # 3 items, header 100k, footer 50k, container 800k → available 650k.
    # 3*200k + 2*20k = 640k → fits at natural.
    assert fit_stack(
        container_h=800_000,
        n=3,
        natural_h=200_000,
        min_h=80_000,
        gap=20_000,
        min_gap=0,
        header_h=100_000,
        footer_h=50_000,
    ) == (200_000, 20_000)


def test_n_one_uses_full_available_height_capped_at_natural() -> None:
    # Single item: gap is irrelevant; height = min(natural, available).
    assert fit_stack(
        container_h=1_000_000,
        n=1,
        natural_h=400_000,
        min_h=100_000,
        gap=20_000,
    ) == (400_000, 0)
    # When natural exceeds available, clamp to available.
    assert fit_stack(
        container_h=300_000,
        n=1,
        natural_h=400_000,
        min_h=100_000,
        gap=20_000,
    ) == (300_000, 0)


def test_text_box_auto_fit_emits_normautofit() -> None:
    from render.shapes import text_box

    xml_off = text_box(1, "x", 0, 0, 100, 100, "hi")
    xml_on = text_box(1, "x", 0, 0, 100, 100, "hi", auto_fit=True)
    assert "normAutofit" not in xml_off
    assert "<a:normAutofit/>" in xml_on


def test_text_box_multi_auto_fit_emits_normautofit() -> None:
    from render.shapes import text_box_multi

    runs: list[tuple[str, int, bool, str]] = [("hi", 10, False, "111111")]
    xml_off = text_box_multi(1, "x", 0, 0, 100, 100, runs)
    xml_on = text_box_multi(1, "x", 0, 0, 100, 100, runs, auto_fit=True)
    assert "normAutofit" not in xml_off
    assert "<a:normAutofit/>" in xml_on
