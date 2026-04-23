from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from xml.etree import ElementTree as ET

SlotKind = Literal["text", "figure", "image", "list", "table", "fixed"]

_NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}

_ROLE_TO_KIND: dict[str, SlotKind] = {
    "title": "text",
    "ctrTitle": "text",
    "subTitle": "text",
    "dt": "text",
    "ftr": "text",
    "sldNum": "text",
    "body": "text",
    "pic": "image",
    "chart": "figure",
    "tbl": "table",
    "obj": "figure",
}


@dataclass(frozen=True)
class EMURect:
    x: int
    y: int
    cx: int
    cy: int


@dataclass(frozen=True)
class Slot:
    id: str
    kind: SlotKind
    rect: EMURect | None
    role: str
    idx: int | None


@dataclass(frozen=True)
class FixedElement:
    rect: EMURect
    element_type: str


@dataclass(frozen=True)
class ExtractionResult:
    slots: list[Slot]
    fixed: list[FixedElement]


class SlotExtractionError(Exception):
    pass


def extract_slots(slide_xml: str | bytes) -> ExtractionResult:
    try:
        root = ET.fromstring(slide_xml)
    except ET.ParseError as e:
        raise SlotExtractionError(str(e)) from e

    sp_tree = root.find(".//p:cSld/p:spTree", _NS)
    if sp_tree is None:
        return ExtractionResult(slots=[], fixed=[])

    slots: list[Slot] = []
    fixed: list[FixedElement] = []
    role_counts: dict[str, int] = {}

    for child in sp_tree:
        tag = _localname(child.tag)
        if tag == "sp":
            ph = child.find("./p:nvSpPr/p:nvPr/p:ph", _NS)
            rect = _read_rect(child)
            if ph is not None:
                role = ph.get("type") or "body"
                idx_attr = ph.get("idx")
                idx = int(idx_attr) if idx_attr is not None else None
                slot_id = _derive_id(role, role_counts)
                kind = _ROLE_TO_KIND.get(role, "text")
                slots.append(Slot(id=slot_id, kind=kind, rect=rect, role=role, idx=idx))
            else:
                if rect is not None:
                    fixed.append(FixedElement(rect=rect, element_type="shape"))
        elif tag == "pic":
            rect = _read_rect(child)
            if rect is not None:
                fixed.append(FixedElement(rect=rect, element_type="pic"))

    return ExtractionResult(slots=slots, fixed=fixed)


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _read_rect(element: ET.Element) -> EMURect | None:
    xfrm = element.find("./p:spPr/a:xfrm", _NS)
    if xfrm is None:
        return None
    off = xfrm.find("./a:off", _NS)
    ext = xfrm.find("./a:ext", _NS)
    if off is None or ext is None:
        return None
    try:
        x = int(off.get("x", ""))
        y = int(off.get("y", ""))
        cx = int(ext.get("cx", ""))
        cy = int(ext.get("cy", ""))
    except ValueError:
        return None
    return EMURect(x=x, y=y, cx=cx, cy=cy)


def _derive_id(role: str, counts: dict[str, int]) -> str:
    n = counts.get(role, 0)
    counts[role] = n + 1
    if role in ("title", "ctrTitle"):
        return "title"
    if role == "subTitle":
        return "subtitle"
    if role == "body":
        return "body_main" if n == 0 else f"body_{n}"
    if role == "ftr":
        return "footer"
    if role == "dt":
        return "date"
    if role == "sldNum":
        return "slide_number"
    if role == "pic":
        return f"image_{n}"
    if role == "tbl":
        return f"table_{n}"
    if role == "chart":
        return f"chart_{n}"
    if role == "obj":
        return f"object_{n}"
    return f"{role}_{n}"
