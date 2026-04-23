"""Shared pytest plumbing for the L3 golden-file visual QA suite (§8.4)."""

from __future__ import annotations

import pytest


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
