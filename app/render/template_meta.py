"""Hand-curated template metadata loader.

The render side ships a JSON file per supported template under
``app/render/templates/<id>.json``. Each file describes the slide
size, the design tokens (colors / fonts / sizes) the layout designer
is expected to follow, and per-page layout data (title box, body
container, decorations to keep vs strip).

For now we only carry the DXDesignSystem template; adding another
template is a matter of dropping a new JSON in the directory and
referencing its `id` from the project / blueprint side.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class SlideSize(_Base):
    cx_emu: int
    cy_emu: int
    label: str | None = None


class Box(_Base):
    """Geometric box used by title / subtitle / body slots and by the
    designer when it composes a slide. EMU values are absolute."""

    x_emu: int
    y_emu: int
    w_emu: int
    h_emu: int
    anchor: str | None = None  # "t" | "ctr" | "b"
    align: str | None = None
    size_pt: int | None = None
    bold: bool | None = None
    color: str | None = None  # palette token or HEX
    auto_fit: bool | None = None
    default_text: str | None = None
    format: str | None = None  # printf-ish for things like "SECTION  {index:02d}"


class TocEntryShape(_Base):
    dx_emu: int = 0
    dy_emu: int = 0
    w_emu: int
    h_emu: int
    size_pt: int | None = None
    bold: bool | None = None
    color: str | None = None


class TocEntryBlock(_Base):
    number_box: TocEntryShape
    title_box: TocEntryShape
    rule_below_dy_emu: int | None = None
    rule_color: str | None = None


class TocItemsBand(_Base):
    x_emu: int
    y_emu: int
    w_emu: int
    h_emu: int
    natural_pitch_emu: int
    entry: TocEntryBlock


class PageMeta(_Base):
    index: int
    layout: str
    title_box: Box | None = None
    subtitle_box: Box | None = None
    section_number_box: Box | None = None
    description_box: Box | None = None
    read_estimate_box: Box | None = None
    title_label_box: Box | None = None
    title_underline_y_emu: int | None = None
    body_box: Box | None = None
    date_box: Box | None = None
    intro_box: Box | None = None
    items_band: TocItemsBand | None = None
    decorations_to_keep: list[str] = Field(default_factory=list)
    decorations_to_strip: list[str] = Field(default_factory=list)


class DesignTokens(_Base):
    primary_hex: str | None = None
    primary_dark_hex: str | None = None
    primary_lt_hex: str | None = None
    muted_hex: str | None = None
    border_hex: str | None = None
    bg_alt_hex: str | None = None
    text_dark_hex: str | None = None
    amber_hex: str | None = None
    green_hex: str | None = None
    title_font: str | None = None
    body_font: str | None = None
    title_pt_cover: int | None = None
    title_pt_section: int | None = None
    title_pt_content: int | None = None
    subtitle_pt: int | None = None
    body_pt: int | None = None
    label_pt: int | None = None
    footer_pt: int | None = None


class PageFooter(_Base):
    x_emu: int
    y_emu: int
    w_emu: int
    h_emu: int
    format: str
    color: str | None = None


class TemplateMeta(_Base):
    id: str
    name: str
    slide_size: SlideSize
    design_tokens: DesignTokens = Field(default_factory=DesignTokens)
    page_footer: PageFooter | None = None
    pages: list[PageMeta] = Field(default_factory=list)

    def page_for(self, layout: str) -> PageMeta | None:
        """Return the page metadata matching a blueprint slide's
        layout (cover / toc / section_divider / content / about /
        disclaimer). When the template has multiple content pages
        (#4 + #4'-style) the first match wins; the layout designer
        is expected to handle variation through its own logic."""
        for page in self.pages:
            if page.layout == layout:
                return page
        return None


@lru_cache(maxsize=8)
def load_template_meta(template_id: str) -> TemplateMeta | None:
    """Load and cache a template's metadata JSON. Returns ``None`` if
    no JSON is shipped for that id — callers fall back to whatever
    legacy heuristics they used before metadata existed."""
    path = _TEMPLATES_DIR / f"{template_id}.json"
    if not path.is_file():
        return None
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    # Strip leading-underscore "_comment" keys so Pydantic doesn't
    # complain in strict mode (and so the JSON file can carry inline
    # documentation).
    _strip_comments(raw)
    return TemplateMeta.model_validate(raw)


def _strip_comments(value: Any) -> None:
    if isinstance(value, dict):
        for k in [k for k in value if isinstance(k, str) and k.startswith("_")]:
            value.pop(k)
        for v in value.values():
            _strip_comments(v)
    elif isinstance(value, list):
        for v in value:
            _strip_comments(v)


def list_template_ids() -> list[str]:
    if not _TEMPLATES_DIR.is_dir():
        return []
    return sorted(p.stem for p in _TEMPLATES_DIR.glob("*.json"))
