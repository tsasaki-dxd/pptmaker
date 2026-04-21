"""Convert .pptx to per-slide JPEG previews via LibreOffice + pdftoppm."""

from __future__ import annotations

import subprocess
from pathlib import Path


def pptx_to_pdf(pptx_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(pptx_path),
        ],
        check=True,
        capture_output=True,
    )
    return out_dir / (pptx_path.stem + ".pdf")


def pdf_to_jpegs(pdf_path: Path, out_dir: Path, dpi: int = 110) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "slide"
    subprocess.run(
        [
            "pdftoppm",
            "-jpeg",
            "-r",
            str(dpi),
            str(pdf_path),
            str(prefix),
        ],
        check=True,
        capture_output=True,
    )
    return sorted(out_dir.glob("slide-*.jpg"))


def pptx_to_jpegs(pptx_path: Path, workdir: Path, dpi: int = 110) -> list[Path]:
    pdf = pptx_to_pdf(pptx_path, workdir)
    return pdf_to_jpegs(pdf, workdir / "jpeg", dpi=dpi)
