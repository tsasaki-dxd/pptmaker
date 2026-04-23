"""Tests for the pptx_assembler that grows/shrinks a template's slide
list to match a blueprint with a per-slide template-page mapping."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from render.pptx_assembler import (
    NS,
    SLIDE_CONTENT_TYPE,
    SLIDE_REL_TYPE,
    assign_default_template_indices,
    derive_slides,
    read_template_slides,
    rewrite_content_types,
    rewrite_presentation_rels,
    rewrite_presentation_xml,
    write_output_slides,
)


def _make_unpacked(tmp: Path, slide_count: int) -> Path:
    """Build a minimal but structurally valid unpacked .pptx tree with
    `slide_count` slide files plus the package-level descriptors that
    the assembler edits."""
    root = tmp / "unpacked"
    (root / "ppt" / "slides" / "_rels").mkdir(parents=True)
    (root / "ppt" / "_rels").mkdir(parents=True)

    for i in range(1, slide_count + 1):
        (root / "ppt" / "slides" / f"slide{i}.xml").write_text(
            f"<sld idx='{i}'/>", encoding="utf-8"
        )
        (root / "ppt" / "slides" / "_rels" / f"slide{i}.xml.rels").write_text(
            f"<rels for='slide{i}'/>", encoding="utf-8"
        )

    pres = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<p:presentation xmlns:p="{NS["p"]}" xmlns:r="{NS["r"]}">'
        "<p:sldIdLst>"
        + "".join(
            f'<p:sldId id="{255 + i}" r:id="rId{i + 1}"/>'
            for i in range(1, slide_count + 1)
        )
        + "</p:sldIdLst>"
        "</p:presentation>"
    )
    (root / "ppt" / "presentation.xml").write_text(pres, encoding="utf-8")

    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Relationships xmlns="{NS["rels"]}">'
        f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
        + "".join(
            f'<Relationship Id="rId{i + 1}" Type="{SLIDE_REL_TYPE}" Target="slides/slide{i}.xml"/>'
            for i in range(1, slide_count + 1)
        )
        + "</Relationships>"
    )
    (root / "ppt" / "_rels" / "presentation.xml.rels").write_text(rels, encoding="utf-8")

    ct = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Types xmlns="{NS["ct"]}">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        + "".join(
            f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="{SLIDE_CONTENT_TYPE}"/>'
            for i in range(1, slide_count + 1)
        )
        + "</Types>"
    )
    (root / "[Content_Types].xml").write_text(ct, encoding="utf-8")
    return root


def test_default_mapping_cycles(tmp_path: Path) -> None:
    bps = [{"index": i} for i in range(1, 8)]
    chosen = assign_default_template_indices(bps, template_slide_count=3)
    # 7 blueprint slides cycling through 3 template pages: 1,2,3,1,2,3,1
    assert chosen == [1, 2, 3, 1, 2, 3, 1]


def test_default_mapping_honors_explicit(tmp_path: Path) -> None:
    bps = [
        {"index": 1, "template_slide_index": 3},
        {"index": 2},
        {"index": 3, "template_slide_index": 99},  # out of range -> falls back
        {"index": 4, "template_slide_index": 1},
    ]
    chosen = assign_default_template_indices(bps, template_slide_count=3)
    # 1: explicit 3
    # 2: cycle (i=1) -> (1 % 3) + 1 = 2
    # 3: 99 invalid -> cycle (i=2) -> (2 % 3) + 1 = 3
    # 4: explicit 1
    assert chosen == [3, 2, 3, 1]


def test_grow_template_to_more_slides(tmp_path: Path) -> None:
    root = _make_unpacked(tmp_path, slide_count=2)
    template_slides = read_template_slides(root)
    chosen = assign_default_template_indices(
        [{"index": 1}, {"index": 2}, {"index": 3}, {"index": 4}, {"index": 5}],
        template_slide_count=2,
    )
    xmls, rels = derive_slides(template_slides, chosen)
    assert len(xmls) == 5

    write_output_slides(root, xmls, rels)
    rewrite_presentation_xml(root, slide_count=5)
    rewrite_presentation_rels(root, slide_count=5)
    rewrite_content_types(root, slide_count=5)

    # 5 slide files now
    slide_files = sorted((root / "ppt" / "slides").glob("slide*.xml"))
    assert [p.name for p in slide_files] == [f"slide{i}.xml" for i in range(1, 6)]
    # 5 rels files
    rels_files = sorted((root / "ppt" / "slides" / "_rels").glob("slide*.xml.rels"))
    assert [p.name for p in rels_files] == [f"slide{i}.xml.rels" for i in range(1, 6)]

    # presentation.xml lists 5 sldIds with new rIds (above existing master rId1)
    pres = ET.parse(root / "ppt" / "presentation.xml").getroot()
    sld_ids = pres.find("p:sldIdLst", NS).findall("p:sldId", NS)
    assert len(sld_ids) == 5
    rids = [s.get(f"{{{NS['r']}}}id") for s in sld_ids]
    assert all(r.startswith("rId") for r in rids)
    assert len(set(rids)) == 5  # unique

    # presentation.xml.rels has 5 slide rels + the preserved slideMaster rel
    rels = ET.parse(root / "ppt" / "_rels" / "presentation.xml.rels").getroot()
    slide_rels = [
        r for r in rels.findall("rels:Relationship", NS) if r.get("Type") == SLIDE_REL_TYPE
    ]
    assert len(slide_rels) == 5
    assert {r.get("Target") for r in slide_rels} == {f"slides/slide{i}.xml" for i in range(1, 6)}
    # Non-slide rel preserved
    assert any(
        r.get("Type") != SLIDE_REL_TYPE for r in rels.findall("rels:Relationship", NS)
    )

    # [Content_Types].xml has 5 slide overrides
    ct = ET.parse(root / "[Content_Types].xml").getroot()
    overrides = [
        o for o in ct.findall("ct:Override", NS) if o.get("ContentType") == SLIDE_CONTENT_TYPE
    ]
    assert len(overrides) == 5
    assert {o.get("PartName") for o in overrides} == {
        f"/ppt/slides/slide{i}.xml" for i in range(1, 6)
    }


def test_shrink_template_to_fewer_slides(tmp_path: Path) -> None:
    root = _make_unpacked(tmp_path, slide_count=5)
    template_slides = read_template_slides(root)
    chosen = assign_default_template_indices(
        [{"index": 1}, {"index": 2}],
        template_slide_count=5,
    )
    xmls, rels = derive_slides(template_slides, chosen)

    write_output_slides(root, xmls, rels)
    rewrite_presentation_xml(root, slide_count=2)
    rewrite_presentation_rels(root, slide_count=2)
    rewrite_content_types(root, slide_count=2)

    slide_files = sorted((root / "ppt" / "slides").glob("slide*.xml"))
    assert [p.name for p in slide_files] == ["slide1.xml", "slide2.xml"]

    pres = ET.parse(root / "ppt" / "presentation.xml").getroot()
    sld_ids = pres.find("p:sldIdLst", NS).findall("p:sldId", NS)
    assert len(sld_ids) == 2


def test_assign_raises_on_zero_template(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        assign_default_template_indices([{"index": 1}], template_slide_count=0)
