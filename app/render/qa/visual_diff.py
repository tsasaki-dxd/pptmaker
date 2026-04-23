"""Visual diff helpers for L3 golden-file QA (Phase 2 design §8.4).

Provides a minimal SSIM implementation on top of Pillow so that tests can
compare rendered slide PNGs against committed goldens without pulling in
``scikit-image`` or ``numpy``. The current version computes a single global
SSIM over the whole image's luminance channel; this is coarse but adequate
for catching layout regressions where large regions change.

TODO: swap in ``skimage.metrics.structural_similarity`` (windowed SSIM) once
we want finer-grained localisation of diffs. That will require adding
``scikit-image`` (+ ``numpy``) to the dev dependencies.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


class VisualDiffUnavailable(RuntimeError):  # noqa: N818 — public name fixed by design §8.4.
    """Raised when the visual diff helper cannot run (missing deps, size mismatch, ...)."""


# SSIM constants per Wang et al. 2004 for images normalised to [0, 255].
_SSIM_K1 = 0.01
_SSIM_K2 = 0.03
_SSIM_L = 255.0
_SSIM_C1 = (_SSIM_K1 * _SSIM_L) ** 2
_SSIM_C2 = (_SSIM_K2 * _SSIM_L) ** 2


def _require_pillow() -> None:
    try:
        import PIL  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised only without Pillow
        raise VisualDiffUnavailable(
            "Pillow is required for visual QA. Install it via `pip install Pillow`."
        ) from exc


def _load_luminance(img_bytes: bytes) -> tuple[PILImage, tuple[int, int]]:
    from PIL import Image

    img = Image.open(io.BytesIO(img_bytes)).convert("L")
    return img, img.size


def _flatten(img: PILImage) -> list[int]:
    # Pillow 14 drops ``getdata``; prefer ``get_flattened_data`` when present.
    getter = getattr(img, "get_flattened_data", None)
    if getter is not None:
        return list(getter())
    return list(img.getdata())


def _mean(pixels: list[int]) -> float:
    return sum(pixels) / len(pixels)


def _variance(pixels: list[int], mean: float) -> float:
    return sum((p - mean) ** 2 for p in pixels) / len(pixels)


def _covariance(a: list[int], b: list[int], mean_a: float, mean_b: float) -> float:
    return sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(len(a))) / len(a)


def compute_ssim(img_a_bytes: bytes, img_b_bytes: bytes) -> float:
    """Return a global SSIM score in [-1.0, 1.0] (1.0 = identical)."""
    _require_pillow()
    img_a, size_a = _load_luminance(img_a_bytes)
    img_b, size_b = _load_luminance(img_b_bytes)

    if size_a != size_b:
        raise VisualDiffUnavailable(
            f"Image size mismatch: {size_a} vs {size_b}; cannot compute SSIM."
        )

    pixels_a: list[int] = _flatten(img_a)
    pixels_b: list[int] = _flatten(img_b)

    mean_a = _mean(pixels_a)
    mean_b = _mean(pixels_b)
    var_a = _variance(pixels_a, mean_a)
    var_b = _variance(pixels_b, mean_b)
    cov_ab = _covariance(pixels_a, pixels_b, mean_a, mean_b)

    numerator = (2 * mean_a * mean_b + _SSIM_C1) * (2 * cov_ab + _SSIM_C2)
    denominator = (mean_a**2 + mean_b**2 + _SSIM_C1) * (var_a + var_b + _SSIM_C2)
    return numerator / denominator


def images_differ(
    img_a_bytes: bytes,
    img_b_bytes: bytes,
    threshold: float = 0.98,
) -> bool:
    """Return True if the two images differ beyond ``threshold`` SSIM."""
    return compute_ssim(img_a_bytes, img_b_bytes) < threshold
