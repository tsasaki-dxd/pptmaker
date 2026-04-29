"""Typography scale tokens for the slide renderer.

Centralizes font sizes so renderers stop hardcoding `size_pt=10` /
`size_pt=12` ad-hoc and reach for a deliberate scale instead. Picked
to give a clear hierarchy on a 16:9 slide at 1280×720 preview while
remaining legible at print resolution:

    micro    8 pt   出典・フッター
    caption  9 pt   補足、注記
    label   10 pt   ラベル、テーブル本文
    body    11 pt   標準本文
    body_lg 12 pt   カードタイトル、重要本文
    title   14 pt   スライドタイトル、強調
    h3      18 pt   セクションタイトル、引用、KPI ラベル
    h2      24 pt   headline_message
    h1      28 pt   KPI 値
    display 36 pt   stat_callout 大数値、ヒーロー

The previous renderer cohort clustered 90% of text at 9–12 pt, which
flattened the visual hierarchy. The new scale has explicit levels for
slide titles, headline conclusions, and metric values so a reader can
see structure at a glance.
"""

from __future__ import annotations

from typing import Literal

ScaleToken = Literal[
    "micro",
    "caption",
    "label",
    "body",
    "body_lg",
    "title",
    "h3",
    "h2",
    "h1",
    "display",
]

TYPE_SCALE: dict[ScaleToken, int] = {
    "micro": 8,
    "caption": 9,
    "label": 10,
    "body": 11,
    "body_lg": 12,
    "title": 14,
    "h3": 18,
    "h2": 24,
    "h1": 28,
    "display": 36,
}

# Line-height ratios (percent). Use "tight" for headings, "normal" for
# body, "relaxed" for paragraphs that need breathing room.
LINE_HEIGHT: dict[str, int] = {
    "tight": 100,
    "normal": 120,
    "relaxed": 140,
}


def pt(token: ScaleToken) -> int:
    """Resolve a scale token to a point size. Wrap raw access so we can
    later swap to template-driven scales without touching every renderer.
    """
    return TYPE_SCALE[token]
