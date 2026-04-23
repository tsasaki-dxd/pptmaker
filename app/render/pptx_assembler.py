"""
Build an output .pptx of N slides derived from a template's M slides
(N can be > or < or == M) using a per-slide template_slide_index map.

The previous renderer just modified template slides 1..N in place. That
broke as soon as the blueprint had more slides than the template, and
gave the user no control over which template page each blueprint slide
used. This module rebuilds the slide list cleanly:

  1. Copy the template's slide{T}.xml (and its _rels) for each blueprint
     slide, in order.
  2. Run the figure renderer on each copy to inject blueprint content.
  3. Rewrite ppt/presentation.xml's <p:sldIdLst>, the matching
     ppt/_rels/presentation.xml.rels slide entries, and the
     [Content_Types].xml slide overrides so the package is internally
     consistent.

Non-slide parts (slideMasters, slideLayouts, theme, media, notesMaster
where it exists) are left untouched.
"""

from __future__ import annotations

import logging
import re
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("slideforge.render.pptx_assembler")

# OOXML namespaces. ElementTree wants the full URI in tags; register
# the prefixes so serialization keeps the original `p:`/`r:` form
# (otherwise PowerPoint won't open the file).
NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "rels": "http://schemas.openxmlformats.org/package/2006/relationships",
}
for prefix, uri in NS.items():
    if prefix in ("p", "r"):
        ET.register_namespace(prefix, uri)
ET.register_namespace("", NS["ct"])  # default for [Content_Types].xml

SLIDE_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
)
SLIDE_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
)


@dataclass
class TemplateSlide:
    """An in-memory copy of one template slide + its rels file."""

    xml: str
    rels_xml: str | None  # may be None if the template slide had no rels file


def read_template_slides(unpacked_root: Path) -> dict[int, TemplateSlide]:
    """Pull every ppt/slides/slide{N}.xml + its _rels/ counterpart."""
    slides_dir = unpacked_root / "ppt" / "slides"
    rels_dir = slides_dir / "_rels"
    out: dict[int, TemplateSlide] = {}
    for slide_path in slides_dir.glob("slide*.xml"):
        m = re.match(r"slide(\d+)\.xml$", slide_path.name)
        if not m:
            continue
        idx = int(m.group(1))
        rels_path = rels_dir / f"{slide_path.name}.rels"
        out[idx] = TemplateSlide(
            xml=slide_path.read_text(encoding="utf-8"),
            rels_xml=rels_path.read_text(encoding="utf-8") if rels_path.exists() else None,
        )
    return out


def write_output_slides(
    unpacked_root: Path,
    slide_xmls: list[str],
    slide_rels: list[str | None],
) -> None:
    """Wipe the existing slide files and write the new ones as
    slide1.xml ... slide{N}.xml.

    Caller is responsible for keeping slide_xmls and slide_rels the
    same length.
    """
    assert len(slide_xmls) == len(slide_rels)
    slides_dir = unpacked_root / "ppt" / "slides"
    rels_dir = slides_dir / "_rels"
    rels_dir.mkdir(parents=True, exist_ok=True)

    # Drop every existing slide{N}.xml + its rels. Other files in
    # ppt/slides/ (uncommon) are left alone.
    for f in slides_dir.glob("slide*.xml"):
        f.unlink()
    for f in rels_dir.glob("slide*.xml.rels"):
        f.unlink()

    for i, (xml, rels) in enumerate(
        zip(slide_xmls, slide_rels, strict=True), start=1
    ):
        (slides_dir / f"slide{i}.xml").write_text(xml, encoding="utf-8")
        if rels is not None:
            (rels_dir / f"slide{i}.xml.rels").write_text(rels, encoding="utf-8")


def rewrite_presentation_xml(unpacked_root: Path, slide_count: int) -> None:
    """Replace <p:sldIdLst> with `slide_count` consecutive entries."""
    pres_path = unpacked_root / "ppt" / "presentation.xml"
    tree = ET.parse(pres_path)
    root = tree.getroot()

    sld_id_lst = root.find("p:sldIdLst", NS)
    if sld_id_lst is None:
        # Should never happen on a real .pptx, but fail loudly if it does
        raise RuntimeError("presentation.xml has no <p:sldIdLst>")

    # Existing IDs to figure out a starting numeric id (must be >= 256
    # per the OOXML spec). We renumber from 256 anyway to keep things
    # tidy — we deleted all old slide rels.
    sld_id_lst.clear()
    base_numeric_id = 256
    base_rid_index = _max_existing_rid(unpacked_root) + 1
    for i in range(slide_count):
        sld = ET.SubElement(sld_id_lst, f"{{{NS['p']}}}sldId")
        sld.set("id", str(base_numeric_id + i))
        sld.set(f"{{{NS['r']}}}id", f"rId{base_rid_index + i}")

    tree.write(pres_path, xml_declaration=True, encoding="UTF-8", short_empty_elements=False)


def _max_existing_rid(unpacked_root: Path) -> int:
    """Highest rIdNN already used in presentation.xml.rels (for non-slide
    entries we're keeping). Returns 0 if no rels exist yet."""
    rels_path = unpacked_root / "ppt" / "_rels" / "presentation.xml.rels"
    if not rels_path.exists():
        return 0
    tree = ET.parse(rels_path)
    max_n = 0
    for rel in tree.getroot().findall("rels:Relationship", NS):
        rid = rel.get("Id", "")
        m = re.match(r"rId(\d+)$", rid)
        if m and rel.get("Type") != SLIDE_REL_TYPE:
            max_n = max(max_n, int(m.group(1)))
    return max_n


def rewrite_presentation_rels(unpacked_root: Path, slide_count: int) -> None:
    """Strip the slide Relationships and add `slide_count` new ones,
    pointing at slide1.xml..slide{N}.xml. Non-slide rels (slideMaster,
    theme, notesMaster, etc.) are preserved."""
    rels_path = unpacked_root / "ppt" / "_rels" / "presentation.xml.rels"
    tree = ET.parse(rels_path)
    root = tree.getroot()

    # Drop existing slide rels
    for rel in list(root.findall("rels:Relationship", NS)):
        if rel.get("Type") == SLIDE_REL_TYPE:
            root.remove(rel)

    # Append new ones, with rIds picked above the highest non-slide rId
    base_rid_index = _max_existing_rid(unpacked_root) + 1
    for i in range(slide_count):
        rel = ET.SubElement(root, f"{{{NS['rels']}}}Relationship")
        rel.set("Id", f"rId{base_rid_index + i}")
        rel.set("Type", SLIDE_REL_TYPE)
        rel.set("Target", f"slides/slide{i + 1}.xml")

    tree.write(rels_path, xml_declaration=True, encoding="UTF-8", short_empty_elements=False)


def rewrite_content_types(unpacked_root: Path, slide_count: int) -> None:
    """Replace the slide <Override> entries in [Content_Types].xml with
    `slide_count` entries pointing at /ppt/slides/slide1..N.xml."""
    ct_path = unpacked_root / "[Content_Types].xml"
    tree = ET.parse(ct_path)
    root = tree.getroot()

    for ov in list(root.findall("ct:Override", NS)):
        if ov.get("ContentType") == SLIDE_CONTENT_TYPE:
            root.remove(ov)

    for i in range(slide_count):
        ov = ET.SubElement(root, f"{{{NS['ct']}}}Override")
        ov.set("PartName", f"/ppt/slides/slide{i + 1}.xml")
        ov.set("ContentType", SLIDE_CONTENT_TYPE)

    tree.write(ct_path, xml_declaration=True, encoding="UTF-8", short_empty_elements=False)


def assign_default_template_indices(
    blueprint_slides: list[dict],
    template_slide_count: int,
) -> list[int]:
    """For each blueprint slide, return the template page it should be
    rendered from. Honors slide.template_slide_index when present and
    in range; otherwise cycles through template pages 1..M.
    """
    if template_slide_count <= 0:
        raise ValueError("template has no slides")
    out: list[int] = []
    for i, s in enumerate(blueprint_slides):
        idx = s.get("template_slide_index")
        if isinstance(idx, int) and 1 <= idx <= template_slide_count:
            out.append(idx)
        else:
            out.append((i % template_slide_count) + 1)
    return out


def derive_slides(
    template_slides: dict[int, TemplateSlide],
    chosen: Iterable[int],
) -> tuple[list[str], list[str | None]]:
    """For each picked template index, return a fresh copy of the
    template slide's XML + rels (both will be modified by the caller)."""
    xmls: list[str] = []
    rels: list[str | None] = []
    for idx in chosen:
        src = template_slides[idx]
        xmls.append(src.xml)
        rels.append(src.rels_xml)
    return xmls, rels


def copy_unpacked(src_root: Path, dst_root: Path) -> Path:
    """Snapshot the unpacked template tree before mutating slide files,
    so we can keep referring to original template slides while rebuilding
    the output.

    Cheaper than re-unpacking the .pptx zip; tree is small (KBs).
    """
    if dst_root.exists():
        shutil.rmtree(dst_root)
    shutil.copytree(src_root, dst_root)
    return dst_root


IMAGE_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
)

_MIME_TO_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
}


def finalize_media(
    unpacked_root: Path,
    registry: object,
    fetcher: object,
) -> list[str]:
    """Materialize image assets from `registry` into the unpacked .pptx tree.

    - Writes bytes to ppt/media/image{N}.{ext} (N = 1-based order of registration).
    - For each slide in registry.slide_usages, appends <Relationship> entries
      to ppt/slides/_rels/slide{idx}.xml.rels (creating the file if needed).
    - Ensures [Content_Types].xml has a <Default Extension="{ext}"
      ContentType="{mime}"/> for every used extension.

    `registry` must expose `.entries: dict[asset_id, ImageAssetDescriptor]` and
    `.slide_usages: dict[int, set[str]]`. `fetcher(s3_key)` must return bytes
    or None if the asset is unavailable (in which case the rel/content-type
    are still written — the image part is omitted and a warning returned).
    """
    warnings: list[str] = []

    asset_ids = list(registry.entries.keys())  # type: ignore[attr-defined]
    asset_to_part: dict[str, tuple[str, str, str]] = {}
    used_exts: dict[str, str] = {}

    media_dir = unpacked_root / "ppt" / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    for idx, asset_id in enumerate(asset_ids, start=1):
        desc = registry.entries[asset_id]  # type: ignore[attr-defined]
        mime = desc.mime
        ext = _MIME_TO_EXT.get(mime)
        if ext is None:
            warnings.append(f"unsupported mime {mime} for asset {asset_id}")
            continue

        data = fetcher(desc.s3_key)  # type: ignore[operator]
        if data is None:
            warnings.append(f"missing bytes for asset {asset_id} (s3_key={desc.s3_key})")
        else:
            (media_dir / f"image{idx}.{ext}").write_bytes(data)

        part_name = f"image{idx}.{ext}"
        rid = f"rId{10000 + idx - 1}"
        asset_to_part[asset_id] = (part_name, ext, rid)
        used_exts[ext] = mime

    rels_dir = unpacked_root / "ppt" / "slides" / "_rels"
    rels_dir.mkdir(parents=True, exist_ok=True)
    for slide_idx, rids_used in registry.slide_usages.items():  # type: ignore[attr-defined]
        rels_path = rels_dir / f"slide{slide_idx}.xml.rels"
        if rels_path.exists():
            tree = ET.parse(rels_path)
            root = tree.getroot()
        else:
            root = ET.Element(f"{{{NS['rels']}}}Relationships")
            tree = ET.ElementTree(root)

        existing_ids = {
            r.get("Id") for r in root.findall("rels:Relationship", NS)
        }

        rid_to_asset: dict[str, str] = {}
        for aid, (_part, _ext, rid) in asset_to_part.items():
            rid_to_asset[rid] = aid

        for rid in sorted(rids_used):
            if rid in existing_ids:
                continue
            aid = rid_to_asset.get(rid)
            if aid is None:
                warnings.append(f"rid {rid} in slide {slide_idx} has no asset mapping")
                continue
            part_name, _ext, _rid = asset_to_part[aid]
            rel = ET.SubElement(root, f"{{{NS['rels']}}}Relationship")
            rel.set("Id", rid)
            rel.set("Type", IMAGE_REL_TYPE)
            rel.set("Target", f"../media/{part_name}")

        tree.write(rels_path, xml_declaration=True, encoding="UTF-8", short_empty_elements=False)

    if used_exts:
        ct_path = unpacked_root / "[Content_Types].xml"
        tree = ET.parse(ct_path)
        root = tree.getroot()
        existing_defaults = {
            d.get("Extension") for d in root.findall("ct:Default", NS)
        }
        for ext, mime in used_exts.items():
            if ext in existing_defaults:
                continue
            default = ET.SubElement(root, f"{{{NS['ct']}}}Default")
            default.set("Extension", ext)
            default.set("ContentType", mime)
        tree.write(ct_path, xml_declaration=True, encoding="UTF-8", short_empty_elements=False)

    return warnings
