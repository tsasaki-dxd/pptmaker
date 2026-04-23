"""Dynamic blueprint system prompt builder.

Phase 2 §5.3: the figure_type catalog in the LLM prompt is derived from the
renderer registry (single source of truth) instead of the hand-maintained
`blueprint_system.txt`. The legacy file is kept as a fallback.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from render.figure_renderers import list_capabilities

PROMPTS_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = PROMPTS_DIR / "blueprint_system.tmpl.txt"

_ENUM_PLACEHOLDER = "{figure_type_enum}"
_SKELETONS_PLACEHOLDER = "{figure_type_skeletons}"


def _render_enum(caps: list[dict[str, object]]) -> str:
    quoted = [f'"{c["figure_type"]}"' for c in caps]
    return " | ".join(quoted)


def _render_skeletons(caps: list[dict[str, object]]) -> str:
    lines = [f"- `{c['figure_type']}`: {c['description']}" for c in caps]
    return "\n".join(lines)


@lru_cache(maxsize=1)
def build_blueprint_system_prompt() -> str:
    """Return the blueprint system prompt with dynamic figure_type catalog.

    Reads `blueprint_system.tmpl.txt` and substitutes `{figure_type_enum}`
    and `{figure_type_skeletons}` from the currently registered renderers.
    Cached — call `build_blueprint_system_prompt.cache_clear()` to refresh
    after mutating the registry (tests, hot reload).
    """
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    caps = list_capabilities()
    enum_block = _render_enum(caps)
    skeletons_block = _render_skeletons(caps)
    return template.replace(_ENUM_PLACEHOLDER, enum_block).replace(
        _SKELETONS_PLACEHOLDER, skeletons_block
    )
