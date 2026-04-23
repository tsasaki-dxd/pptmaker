"""
Figure renderer registry.

Import side effects register each concrete renderer in the global REGISTRY.
"""

from . import (  # noqa: F401
    bullet_list,
    cards_grid,
    comparison,
    matrix_2x2,
    pyramid,
    stat_callout,
    swot,
    table,
    timeline,
    two_column,
)
from .base import FigureRenderer
from .registry import REGISTRY, get, register  # noqa: F401


def renderer_for(figure_type: str) -> FigureRenderer:
    return get(figure_type)


def list_capabilities() -> list[dict[str, object]]:
    return [r.capability() for r in REGISTRY.values()]
