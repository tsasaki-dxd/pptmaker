from __future__ import annotations

import pytest

from render.slot_extractor import (
    EMURect,
    ExtractionResult,
    SlotExtractionError,
    extract_slots,
)

_SLIDE_OPEN = (
    '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    "<p:cSld><p:spTree>"
)
_SLIDE_CLOSE = "</p:spTree></p:cSld></p:sld>"


def _sp(ph_type: str | None, idx: str | None, xfrm: tuple[int, int, int, int] | None) -> str:
    ph_attrs = ""
    if ph_type is not None:
        ph_attrs += f' type="{ph_type}"'
    if idx is not None:
        ph_attrs += f' idx="{idx}"'
    ph = f"<p:ph{ph_attrs}/>" if ph_type is not None or idx is not None else "<p:ph/>"
    xfrm_xml = ""
    if xfrm is not None:
        x, y, cx, cy = xfrm
        xfrm_xml = (
            f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        )
    return (
        f"<p:sp><p:nvSpPr><p:cNvPr id='1' name='x'/><p:cNvSpPr/>"
        f"<p:nvPr>{ph}</p:nvPr></p:nvSpPr>"
        f"<p:spPr>{xfrm_xml}</p:spPr></p:sp>"
    )


def _bare_sp(xfrm: tuple[int, int, int, int] | None) -> str:
    xfrm_xml = ""
    if xfrm is not None:
        x, y, cx, cy = xfrm
        xfrm_xml = (
            f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        )
    return (
        f"<p:sp><p:nvSpPr><p:cNvPr id='1' name='x'/><p:cNvSpPr/>"
        f"<p:nvPr/></p:nvSpPr>"
        f"<p:spPr>{xfrm_xml}</p:spPr></p:sp>"
    )


def _pic(xfrm: tuple[int, int, int, int]) -> str:
    x, y, cx, cy = xfrm
    return (
        f"<p:pic><p:nvPicPr><p:cNvPr id='2' name='logo'/><p:cNvPicPr/>"
        f"<p:nvPr/></p:nvPicPr><p:blipFill/>"
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/>'
        f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm></p:spPr></p:pic>'
    )


def _slide(*children: str) -> str:
    return _SLIDE_OPEN + "".join(children) + _SLIDE_CLOSE


def test_title_body_footer_placeholders() -> None:
    xml = _slide(
        _sp("title", "0", (100, 200, 300, 400)),
        _sp("body", "1", (500, 600, 700, 800)),
        _sp("ftr", "10", (10, 20, 30, 40)),
    )
    result = extract_slots(xml)
    assert isinstance(result, ExtractionResult)
    assert len(result.slots) == 3
    assert result.fixed == []
    s_title, s_body, s_ftr = result.slots
    assert s_title.id == "title"
    assert s_title.kind == "text"
    assert s_title.rect == EMURect(100, 200, 300, 400)
    assert s_title.role == "title"
    assert s_title.idx == 0
    assert s_body.id == "body_main"
    assert s_body.kind == "text"
    assert s_body.role == "body"
    assert s_ftr.id == "footer"
    assert s_ftr.role == "ftr"


def test_two_body_placeholders_numbered() -> None:
    xml = _slide(
        _sp("body", "1", (1, 2, 3, 4)),
        _sp("body", "2", (5, 6, 7, 8)),
    )
    result = extract_slots(xml)
    assert [s.id for s in result.slots] == ["body_main", "body_1"]


def test_title_plus_pic_as_fixed_logo() -> None:
    xml = _slide(
        _sp("title", "0", (10, 20, 30, 40)),
        _pic((99, 88, 77, 66)),
    )
    result = extract_slots(xml)
    assert len(result.slots) == 1
    assert result.slots[0].id == "title"
    assert len(result.fixed) == 1
    assert result.fixed[0].element_type == "pic"
    assert result.fixed[0].rect == EMURect(99, 88, 77, 66)


def test_placeholder_without_xfrm_has_none_rect() -> None:
    xml = _slide(_sp("body", "1", None))
    result = extract_slots(xml)
    assert len(result.slots) == 1
    assert result.slots[0].rect is None
    assert result.slots[0].role == "body"


def test_obj_placeholder_is_figure_kind() -> None:
    xml = _slide(_sp("obj", "2", (1, 2, 3, 4)))
    result = extract_slots(xml)
    assert len(result.slots) == 1
    slot = result.slots[0]
    assert slot.kind == "figure"
    assert slot.id == "object_0"
    assert slot.idx == 2
    assert slot.role == "obj"


def test_malformed_xml_raises() -> None:
    with pytest.raises(SlotExtractionError):
        extract_slots("<p:sld><p:cSld><not-closed>")


def test_sp_without_ph_is_fixed_shape() -> None:
    xml = _slide(_bare_sp((1, 2, 3, 4)))
    result = extract_slots(xml)
    assert result.slots == []
    assert len(result.fixed) == 1
    assert result.fixed[0].element_type == "shape"


def test_ph_without_type_defaults_to_body() -> None:
    xml = _slide(_sp(None, "5", (1, 2, 3, 4)))
    result = extract_slots(xml)
    assert len(result.slots) == 1
    assert result.slots[0].role == "body"
    assert result.slots[0].id == "body_main"
    assert result.slots[0].idx == 5
