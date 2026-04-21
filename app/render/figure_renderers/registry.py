"""Global renderer registry."""

from __future__ import annotations

from .base import FigureRenderer

REGISTRY: dict[str, FigureRenderer] = {}


def register(cls: type[FigureRenderer]) -> type[FigureRenderer]:
    """Class decorator to register a FigureRenderer subclass."""
    inst = cls()
    if not inst.figure_type:
        raise ValueError(f"{cls.__name__} must define figure_type")
    if inst.figure_type in REGISTRY:
        raise ValueError(f"Duplicate figure_type: {inst.figure_type}")
    REGISTRY[inst.figure_type] = inst
    return cls


def get(figure_type: str) -> FigureRenderer:
    if figure_type not in REGISTRY:
        raise KeyError(f"Unknown figure_type: {figure_type}")
    return REGISTRY[figure_type]
