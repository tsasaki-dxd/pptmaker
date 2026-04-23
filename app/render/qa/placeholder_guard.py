from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from xml.etree import ElementTree as ET

DEFAULT_JA_PLACEHOLDER_STRINGS: tuple[str, ...] = (
    "クリックしてタイトルを入力",
    "クリックしてテキストを入力",
    "クリックしてサブタイトルを入力",
    "タイトルを入力",
    "テキストを入力",
    "本文をここに入れる",
    "本文を入力",
    "ここにテキスト",
    "サブタイトル",
)

DEFAULT_EN_PLACEHOLDER_STRINGS: tuple[str, ...] = (
    "Click to add title",
    "Click to add text",
    "Click to add subtitle",
    "Click here to add text",
    "Lorem ipsum",
    "Your title here",
    "Your text here",
)

DEFAULT_PLACEHOLDER_STRINGS: tuple[str, ...] = (
    DEFAULT_JA_PLACEHOLDER_STRINGS + DEFAULT_EN_PLACEHOLDER_STRINGS
)

_NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


class PlaceholderScanError(Exception):
    """Raised when slide XML cannot be parsed."""


@dataclass(frozen=True)
class Leak:
    shape_id: str | None
    offending_text: str
    snippet: str


def scan_placeholder_leak(
    slide_xml: str | bytes,
    needles: Sequence[str] = DEFAULT_PLACEHOLDER_STRINGS,
) -> list[Leak]:
    """Scan slide XML and return placeholder-text leaks."""
    try:
        root = ET.fromstring(slide_xml)
    except ET.ParseError as exc:
        raise PlaceholderScanError(str(exc)) from exc

    leaks: list[Leak] = []
    for sp in root.iter(f"{{{_NS['p']}}}sp"):
        shape_id = _shape_id(sp)
        for paragraph in sp.iter(f"{{{_NS['a']}}}p"):
            text = _paragraph_text(paragraph)
            if not text:
                continue
            snippet = text[:80]
            for needle in needles:
                if needle in text:
                    leaks.append(
                        Leak(
                            shape_id=shape_id,
                            offending_text=needle,
                            snippet=snippet,
                        )
                    )
    return leaks


def _shape_id(sp: ET.Element) -> str | None:
    cnvpr = sp.find("./p:nvSpPr/p:cNvPr", _NS)
    if cnvpr is None:
        return None
    return cnvpr.get("id")


def _paragraph_text(paragraph: ET.Element) -> str:
    parts: list[str] = []
    for t in paragraph.iter(f"{{{_NS['a']}}}t"):
        if t.text:
            parts.append(t.text)
    return "".join(parts)
