"""Named palette registry — sample-gallery and template-binding hub.

Each named palette is a `Palette` instance with the same field names
(`purple`, `purple_lt`, `purple_dk`, …); the labels stay because the
field names are referenced from layout_designer prompts and
`resolve_palette_color` token map. The underlying hexes change per
brand. Field 'purple' is a stable token that means "primary brand
color" — even when the brand is navy.

Used by:
  * scripts/generate_samples.py — iterates every entry to emit a
    per-template sample set so the /samples gallery can demonstrate
    template-specific theming.
  * Future production path can map a TemplateRow.brand_id to one of
    these names when the template's own theme1.xml doesn't carry
    full palette information.
"""

from __future__ import annotations

from dataclasses import dataclass

from .shapes import Palette


@dataclass(frozen=True)
class NamedPalette:
    """A palette with display metadata for the gallery selector."""

    id: str
    label: str
    palette: Palette


# DX デザインシステム株式会社 — current production default. Purple
# primary, amber/green secondary, designed to feel modern & creative.
DXDESIGN_PALETTE = NamedPalette(
    id="dxdesign",
    label="DXデザインシステム",
    palette=Palette(),  # field defaults already match
)


# DX 会計事務所 — professional / financial-services tone. Corporate
# navy primary with sophisticated gold accent and deep teal secondary.
# Conservative palette intended for accounting / advisory decks.
DXACCOUNTING_PALETTE = NamedPalette(
    id="dxaccounting",
    label="DX会計事務所",
    palette=Palette(
        purple="2E5C8A",       # corporate navy (primary)
        purple_lt="8FAFD0",    # soft navy
        purple_dk="1A3A5F",    # deep navy
        purple_bg="EEF2F8",    # very light navy bg
        black="2A2E3A",        # cooler near-black
        dark="4A5060",         # slate dark
        muted="8E97A8",        # cool muted gray
        border="DCE2EB",       # light cool border
        bg_alt="FFFFFF",
        amber="BF9B5A",        # professional gold accent
        green="4F8470",        # deep teal-green
    ),
)


# Ordered registry. Order = display order in the gallery selector and
# default-first in the samples generator. Production templates eventually
# bind to these by id (TemplateRow.palette_id or via design_tokens).
NAMED_PALETTES: tuple[NamedPalette, ...] = (
    DXDESIGN_PALETTE,
    DXACCOUNTING_PALETTE,
)


def get_named_palette(palette_id: str) -> NamedPalette | None:
    for np in NAMED_PALETTES:
        if np.id == palette_id:
            return np
    return None
