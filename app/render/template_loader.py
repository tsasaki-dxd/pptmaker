"""
PPTX template unpack / pack helpers.

A PPTX is a zip archive. This module handles safe unzip (zip-slip / zip-bomb
protection) and re-pack while preserving original [Content_Types].xml and
relationships.
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

MAX_ZIP_ENTRIES = 2000
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
MAX_FILE_BYTES = 100 * 1024 * 1024


class TemplateError(Exception):
    pass


@dataclass
class UnpackedTemplate:
    root: Path

    def slide_path(self, index: int) -> Path:
        """Return path to ppt/slides/slideN.xml."""
        return self.root / "ppt" / "slides" / f"slide{index}.xml"

    def read_slide(self, index: int) -> str:
        return self.slide_path(index).read_text(encoding="utf-8")

    def write_slide(self, index: int, xml: str) -> None:
        self.slide_path(index).write_text(xml, encoding="utf-8")


def safe_unpack(pptx_path: Path, dest_dir: Path) -> UnpackedTemplate:
    """Extract a .pptx into dest_dir with safety checks."""
    if not pptx_path.is_file():
        raise TemplateError(f"not a file: {pptx_path}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest_dir.resolve()

    with zipfile.ZipFile(pptx_path) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise TemplateError("too many entries in zip")
        total = 0
        for info in infos:
            if info.file_size > MAX_FILE_BYTES:
                raise TemplateError(f"entry too large: {info.filename}")
            total += info.file_size
            if total > MAX_UNCOMPRESSED_BYTES:
                raise TemplateError("uncompressed size exceeds limit")

            # Zip-slip guard
            target = (dest_resolved / info.filename).resolve()
            if dest_resolved not in target.parents and target != dest_resolved:
                raise TemplateError(f"zip-slip attempt: {info.filename}")

        zf.extractall(dest_dir)

    return UnpackedTemplate(root=dest_dir)


def repack(unpacked: UnpackedTemplate, out_path: Path) -> Path:
    """Pack the unpacked tree back into a .pptx."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_zip = Path(tempfile.mkstemp(suffix=".pptx.tmp")[1])

    with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(unpacked.root.rglob("*")):
            if path.is_file():
                arcname = path.relative_to(unpacked.root).as_posix()
                zf.write(path, arcname)

    shutil.move(tmp_zip, out_path)
    return out_path
