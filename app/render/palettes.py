"""Named palette + template registry for the sample gallery.

Each named entry binds a `Palette` (body colors) to a `.pptx`
template path (slide chrome). The same field names (`purple`,
`purple_lt`, `purple_dk`, …) stay across templates because the field
names are referenced from layout_designer prompts and
`resolve_palette_color` token maps. The underlying hexes change per
brand — field 'purple' is the stable token for "primary brand
color", even when the brand is teal-blue.

Used by:
  * scripts/generate_samples.py — iterates every entry to emit a
    per-template sample set so the /samples gallery can demonstrate
    template-specific theming end-to-end (chrome + body).
  * Future production path can map a TemplateRow.brand_id to one of
    these names.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .shapes import Palette

_DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"


@dataclass(frozen=True)
class NamedPalette:
    """A palette + its slide-chrome template, with display metadata
    for the gallery selector."""

    id: str
    label: str
    palette: Palette
    template_path: Path
    # The 1-based slide index inside ``template_path`` that the
    # samples generator should clone as the body-content layout.
    # DXDesignSystem ships with the content page at slide 4; sister
    # templates may differ, so each entry declares its own.
    content_slide_index: int = 4


# DX デザインシステム株式会社 — current production default. Purple
# primary, amber/green secondary, designed to feel modern & creative.
DXDESIGN_PALETTE = NamedPalette(
    id="dxdesign",
    label="DXデザインシステム",
    palette=Palette(),  # field defaults already match
    template_path=_DOCS_DIR / "DXDesignSystem_Template.pptx",
)


# DX デザイン会計事務所 — professional / financial-services tone.
# Body palette derived from the chrome accent that the template ships
# with (#0080B0 — corporate cyan-blue) so figure shapes (KPI cards,
# SWOT pills, charts) tonally match the slide chrome (eyebrow, accent
# bar, page numbering). Amber + green stay generic for delta / status
# indicators.
DXACCOUNTING_PALETTE = NamedPalette(
    id="dxaccounting",
    label="DXデザイン会計事務所",
    palette=Palette(
        purple="0080B0",       # corporate cyan-blue (matches template chrome)
        purple_lt="7FB8D8",    # soft cyan
        purple_dk="00567A",    # deeper cyan-blue for emphasis
        purple_bg="EAF3F8",    # very light cyan tint
        black="2F3A42",        # cool near-black (matches chrome)
        dark="4A5560",         # slate dark
        muted="7A8894",        # matches chrome muted
        border="E1E8EC",       # matches chrome border
        bg_alt="FFFFFF",
        amber="BF9B5A",        # professional gold accent
        green="4F8470",        # deep teal-green
    ),
    template_path=_DOCS_DIR / "DXDesignAccounting_Template.pptx",
)


# Ordered registry. Order = display order in the gallery selector and
# default-first in the samples generator.
NAMED_PALETTES: tuple[NamedPalette, ...] = (
    DXDESIGN_PALETTE,
    DXACCOUNTING_PALETTE,
)


def get_named_palette(palette_id: str) -> NamedPalette | None:
    for np in NAMED_PALETTES:
        if np.id == palette_id:
            return np
    return None
