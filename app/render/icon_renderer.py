"""SVG → PNG icon rasterizer for the slide renderer.

Reads Lucide SVGs from ``app/render/icons/lucide/<name>.svg``,
substitutes the stroke/fill color for theme integration, and
rasterizes to PNG via cairosvg. Results are LRU-cached so the same
(name, color, size) combo is rasterized only once per Lambda warm
container.

PowerPoint <2017 cannot embed raw SVG; we ship PNG as the lowest
common denominator. Using <asvg:svgBlip> with an SVG fallback (modern
PowerPoint) is a follow-up — the picture pipeline already accepts
PNG, so this gives us 100% compatibility today with no XML changes.

Lucide icons are MIT-licensed; bundled copy at
``app/render/icons/lucide/`` was fetched from the upstream repo at
https://github.com/lucide-icons/lucide.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("slideforge.icon_renderer")

ICONS_DIR = Path(__file__).parent / "icons" / "lucide"


def _list_catalog() -> list[str]:
    if not ICONS_DIR.exists():
        return []
    return sorted(p.stem for p in ICONS_DIR.glob("*.svg"))


# Public catalog of available icon names. Imported by layout_designer
# for the LLM prompt and by figure_renderers for default lookups.
ICON_CATALOG: list[str] = _list_catalog()
_CATALOG_SET: frozenset[str] = frozenset(ICON_CATALOG)


def is_known(name: str) -> bool:
    return name in _CATALOG_SET


_HEX_RE = re.compile(r"^#?([0-9A-Fa-f]{6})$")


def _normalize_hex(color: str) -> str:
    """Accept 'A78BFA', '#A78BFA', or '#a78bfa' and return '#A78BFA'."""
    m = _HEX_RE.match(color.strip())
    if not m:
        raise ValueError(f"icon color must be 6-char HEX, got {color!r}")
    return f"#{m.group(1).upper()}"


def _load_svg(name: str) -> str:
    if name not in _CATALOG_SET:
        raise ValueError(
            f"unknown icon {name!r}; not in catalog "
            f"({len(ICON_CATALOG)} icons available)"
        )
    return (ICONS_DIR / f"{name}.svg").read_text(encoding="utf-8")


def _recolor_svg(svg: str, hex_color: str) -> str:
    """Replace currentColor / hardcoded strokes with the requested hex.

    Lucide SVGs use stroke="currentColor" + fill="none". Replacing
    currentColor is enough; we also stamp a stroke attribute on the
    <svg> root as a belt-and-suspenders measure for any nested element
    that inherited from CSS context we don't have.
    """
    out = svg.replace('"currentColor"', f'"{hex_color}"')
    if 'stroke="' not in out.split(">", 1)[0]:
        # Inject stroke on the root <svg ...> tag.
        out = out.replace("<svg", f'<svg stroke="{hex_color}"', 1)
    return out


@lru_cache(maxsize=256)
def render_icon_png(name: str, color: str = "#000000", size_px: int = 256) -> bytes:
    """Rasterize a Lucide icon to PNG bytes.

    Args:
        name: icon identifier (must be in ICON_CATALOG).
        color: 6-char HEX (with or without leading '#'). All strokes /
               fills set to ``currentColor`` are recolored to this.
        size_px: output resolution. 256 is a good middle ground —
                 small enough to embed cheaply, large enough that
                 PowerPoint downscales cleanly to icon sizes (16–48
                 EMU at 100% zoom).

    Returns:
        PNG bytes.

    Raises:
        ValueError: if ``name`` isn't in the catalog or color isn't a
                    valid 6-char HEX.
        RuntimeError: if cairosvg isn't installed (only checked here so
                      pure-text test environments don't have to).
    """
    hex_color = _normalize_hex(color)
    svg = _recolor_svg(_load_svg(name), hex_color)

    try:
        # cairosvg is the only render-side dep that pulls in libcairo.
        # Imported lazily so unit tests that don't touch icons can run
        # in environments without it.
        import cairosvg  # type: ignore[import-untyped]
    except ImportError as e:
        raise RuntimeError(
            "cairosvg is required for icon rendering — "
            "install with `pip install cairosvg`"
        ) from e

    png_bytes = cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        output_width=size_px,
        output_height=size_px,
    )
    assert isinstance(png_bytes, bytes)
    return png_bytes


def asset_id_for(name: str, color: str) -> str:
    """Stable asset_id for MediaRegistry dedup. Same icon + same color
    always returns the same id, so PowerPoint embeds the PNG once and
    references it from every slide that uses it."""
    return f"icon-{name}-{_normalize_hex(color).lstrip('#').lower()}"
