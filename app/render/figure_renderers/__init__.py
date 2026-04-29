"""
Figure renderer registry.

Import side effects register each concrete renderer in the global REGISTRY.
"""

from . import (  # noqa: F401
    bar_chart,
    bullet_list,
    business_canvas,
    cards_grid,
    comparison,
    cost_breakdown,
    flowchart,
    gantt,
    icon_list,
    image_slot,
    kpi_dashboard,
    line_chart,
    matrix_2x2,
    org_chart,
    pie_chart,
    process_flow,
    pull_quote,
    pyramid,
    scheme_diagram,
    spider_map,
    stack_bar,
    stat_callout,
    swot,
    system_map,
    table,
    timeline,
    two_column,
    value_chain,
    value_flow,
    waterfall,
)
from .base import FigureRenderer
from .registry import REGISTRY, get, register  # noqa: F401


def renderer_for(figure_type: str) -> FigureRenderer:
    return get(figure_type)


def list_capabilities() -> list[dict[str, object]]:
    return [r.capability() for r in REGISTRY.values()]
