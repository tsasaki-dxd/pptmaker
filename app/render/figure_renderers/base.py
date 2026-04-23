"""
Figure renderer abstract base class (plugin IF).

See docs/04_template_and_plugin.md §7 for the design rationale.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from ..shapes import Palette

if TYPE_CHECKING:
    from ..media import MediaRegistry


@dataclass(frozen=True)
class EMUBox:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class RenderContext:
    """Runtime state passed to every renderer."""

    palette: Palette
    font: str
    next_shape_id: int
    media: MediaRegistry | None = None
    slide_index: int | None = None


@dataclass
class RenderOutput:
    """Return value from a renderer: XML fragments and the next shape id."""

    shapes_xml: list[str]
    next_shape_id: int


class FigureRenderer(ABC):
    """Plugin-style renderer for a single figure_type.

    Subclasses should register themselves via @register in registry.py.
    """

    figure_type: str = ""
    description: str = ""
    input_schema_example: ClassVar[dict[str, Any]] = {}

    @abstractmethod
    def validate(self, content: dict[str, Any]) -> ValidationResult: ...

    @abstractmethod
    def render(
        self,
        content: dict[str, Any],
        container: EMUBox,
        ctx: RenderContext,
    ) -> RenderOutput: ...

    def capability(self) -> dict[str, Any]:
        """Expose metadata for the LLM's figure_type catalog."""
        return {
            "figure_type": self.figure_type,
            "description": self.description,
            "input_schema_example": self.input_schema_example,
        }
