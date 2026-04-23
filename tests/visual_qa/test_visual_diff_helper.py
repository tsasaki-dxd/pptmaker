"""Toy tests for the SSIM helper — runnable without LibreOffice."""

from __future__ import annotations

import io

import pytest

from render.qa.visual_diff import (
    VisualDiffUnavailable,
    compute_ssim,
    images_differ,
)

PIL = pytest.importorskip("PIL", reason="Pillow not installed; visual QA scaffold skipped.")


def _png_bytes(color: int, size: tuple[int, int] = (32, 32)) -> bytes:
    from PIL import Image

    img = Image.new("L", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_identical_images_score_near_one() -> None:
    png = _png_bytes(128)
    assert compute_ssim(png, png) >= 0.99
    assert images_differ(png, png) is False


def test_white_vs_black_flags_as_different() -> None:
    white = _png_bytes(255)
    black = _png_bytes(0)
    score = compute_ssim(white, black)
    assert score < 0.98
    assert images_differ(white, black) is True


def test_size_mismatch_raises() -> None:
    small = _png_bytes(128, size=(16, 16))
    large = _png_bytes(128, size=(32, 32))
    with pytest.raises(VisualDiffUnavailable, match="size mismatch"):
        compute_ssim(small, large)
