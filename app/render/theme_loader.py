from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_THEME_PATH = "ppt/theme/theme1.xml"

_COLOR_SLOTS: tuple[str, ...] = (
    "dk1",
    "lt1",
    "dk2",
    "lt2",
    "accent1",
    "accent2",
    "accent3",
    "accent4",
    "accent5",
    "accent6",
    "hlink",
    "folHlink",
)

_DARK_DEFAULT = "000000"
_LIGHT_DEFAULT = "FFFFFF"


class ThemeParseError(Exception):
    pass


@dataclass(frozen=True)
class ThemeColors:
    dk1: str
    lt1: str
    dk2: str
    lt2: str
    accent1: str
    accent2: str
    accent3: str
    accent4: str
    accent5: str
    accent6: str
    hlink: str
    fol_hlink: str


@dataclass(frozen=True)
class ThemeFonts:
    major_latin: str
    major_ea: str
    major_cs: str
    minor_latin: str
    minor_ea: str
    minor_cs: str


@dataclass(frozen=True)
class Theme:
    colors: ThemeColors
    fonts: ThemeFonts


def load_theme(pptx_bytes: bytes) -> Theme:
    # Multiple theme*.xml variants may exist; only theme1.xml is consulted.
    try:
        with zipfile.ZipFile(io.BytesIO(pptx_bytes)) as zf:
            try:
                xml_bytes = zf.read(_THEME_PATH)
            except KeyError as e:
                raise ThemeParseError(f"missing {_THEME_PATH}") from e
    except zipfile.BadZipFile as e:
        raise ThemeParseError("invalid pptx zip") from e
    return parse_theme_xml(xml_bytes)


def parse_theme_xml(theme_xml: bytes | str) -> Theme:
    try:
        root = ET.fromstring(theme_xml)
    except ET.ParseError as e:
        raise ThemeParseError("malformed theme xml") from e
    return Theme(colors=_parse_colors(root), fonts=_parse_fonts(root))


def _q(tag: str) -> str:
    return f"{{{_NS}}}{tag}"


def _default_for(slot: str) -> str:
    if slot.startswith("dk") or slot == "hlink" or slot == "folHlink":
        return _DARK_DEFAULT
    return _LIGHT_DEFAULT


def _resolve_color(slot_elem: ET.Element | None, slot: str) -> str:
    if slot_elem is None:
        return _default_for(slot)
    srgb = slot_elem.find(_q("srgbClr"))
    if srgb is not None:
        val = srgb.get("val")
        if val:
            return val.upper()
    sys_clr = slot_elem.find(_q("sysClr"))
    if sys_clr is not None:
        last = sys_clr.get("lastClr")
        if last:
            return last.upper()
    return _default_for(slot)


def _parse_colors(root: ET.Element) -> ThemeColors:
    scheme = root.find(f".//{_q('clrScheme')}")
    resolved: dict[str, str] = {}
    for slot in _COLOR_SLOTS:
        elem = scheme.find(_q(slot)) if scheme is not None else None
        resolved[slot] = _resolve_color(elem, slot)
    return ThemeColors(
        dk1=resolved["dk1"],
        lt1=resolved["lt1"],
        dk2=resolved["dk2"],
        lt2=resolved["lt2"],
        accent1=resolved["accent1"],
        accent2=resolved["accent2"],
        accent3=resolved["accent3"],
        accent4=resolved["accent4"],
        accent5=resolved["accent5"],
        accent6=resolved["accent6"],
        hlink=resolved["hlink"],
        fol_hlink=resolved["folHlink"],
    )


def _typeface(parent: ET.Element | None, tag: str) -> str:
    if parent is None:
        return ""
    el = parent.find(_q(tag))
    if el is None:
        return ""
    return el.get("typeface", "") or ""


def _parse_fonts(root: ET.Element) -> ThemeFonts:
    scheme = root.find(f".//{_q('fontScheme')}")
    major = scheme.find(_q("majorFont")) if scheme is not None else None
    minor = scheme.find(_q("minorFont")) if scheme is not None else None
    return ThemeFonts(
        major_latin=_typeface(major, "latin"),
        major_ea=_typeface(major, "ea"),
        major_cs=_typeface(major, "cs"),
        minor_latin=_typeface(minor, "latin"),
        minor_ea=_typeface(minor, "ea"),
        minor_cs=_typeface(minor, "cs"),
    )
