"""Shared pytest plumbing for the L3 golden-file visual QA suite (§8.4)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from render.qa.visual_diff import compute_ssim

_GOLDEN_ROOT = Path(__file__).parent / "golden"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Overwrite the on-disk golden PNGs with freshly rendered output.",
    )


@pytest.fixture
def update_golden(request: pytest.FixtureRequest) -> bool:
    """Return True when the suite should refresh golden assets instead of asserting."""
    return bool(request.config.getoption("--update-golden"))


@pytest.fixture
def golden_dir(request: pytest.FixtureRequest, update_golden: bool) -> Path:
    """Per-test golden directory under ``tests/visual_qa/golden/<test_name>/``."""
    test_name = request.node.name
    path = _GOLDEN_ROOT / test_name
    if update_golden:
        path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def assert_golden_match(
    request: pytest.FixtureRequest,
    update_golden: bool,
) -> Callable[..., None]:
    """Return a callable that compares rendered PNGs against committed goldens."""
    test_name = request.node.name

    def _check(pngs: list[bytes], *, case_name: str, threshold: float = 0.98) -> None:
        base_dir = _GOLDEN_ROOT / test_name / case_name

        if update_golden:
            base_dir.mkdir(parents=True, exist_ok=True)
            for idx, png in enumerate(pngs, start=1):
                (base_dir / f"slide_{idx:02d}.png").write_bytes(png)
            return

        if not base_dir.is_dir():
            pytest.fail(
                f"Golden baseline missing at {base_dir}. "
                f"Re-run with `--update-golden` to create it."
            )

        baseline_paths = sorted(base_dir.glob("slide_*.png"))
        if not baseline_paths:
            pytest.fail(
                f"Golden baseline at {base_dir} is empty. "
                f"Re-run with `--update-golden` to populate it."
            )

        if len(baseline_paths) != len(pngs):
            pytest.fail(
                f"Slide count mismatch for {case_name}: "
                f"rendered {len(pngs)} vs baseline {len(baseline_paths)}."
            )

        for idx, (rendered, baseline_path) in enumerate(
            zip(pngs, baseline_paths, strict=True), start=1
        ):
            score = compute_ssim(rendered, baseline_path.read_bytes())
            if score < threshold:
                pytest.fail(
                    f"SSIM {score:.4f} below threshold {threshold} for "
                    f"{case_name}/slide_{idx:02d}.png."
                )

    return _check
