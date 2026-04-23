"""Render .pptx bytes to per-slide PNG bytes via LibreOffice + pdftoppm (Phase 2 §8.4)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

_LO_PROFILE_DIR = "file:///tmp/lo-profile-qa"


class PptxRenderUnavailable(RuntimeError):  # noqa: N818 — public name fixed by design §8.4.
    """Raised when the PPTX→PNG pipeline cannot run (missing binaries, timeout, ...)."""


def _require_binaries() -> tuple[str, str]:
    soffice = shutil.which("soffice")
    pdftoppm = shutil.which("pdftoppm")
    if soffice is None:
        raise PptxRenderUnavailable(
            "`soffice` binary not found on PATH; install LibreOffice to run visual QA."
        )
    if pdftoppm is None:
        raise PptxRenderUnavailable(
            "`pdftoppm` binary not found on PATH; install poppler-utils to run visual QA."
        )
    return soffice, pdftoppm


def _run(cmd: list[str], *, timeout_s: int) -> None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise PptxRenderUnavailable(
            f"command timed out after {timeout_s}s: {' '.join(cmd)}"
        ) from exc
    if proc.returncode != 0:
        raise PptxRenderUnavailable(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )


def render_pptx_to_pngs(
    pptx_bytes: bytes,
    *,
    dpi: int = 150,
    timeout_s: int = 60,
) -> list[bytes]:
    """Render each slide of a .pptx to a PNG byte string."""
    soffice, pdftoppm = _require_binaries()

    with tempfile.TemporaryDirectory(prefix="pptx_qa_") as tmp:
        tmpdir = Path(tmp)
        pptx_path = tmpdir / "input.pptx"
        pptx_path.write_bytes(pptx_bytes)

        pdf_dir = tmpdir / "pdf"
        pdf_dir.mkdir()
        _run(
            [
                soffice,
                "--headless",
                f"-env:UserInstallation={_LO_PROFILE_DIR}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(pdf_dir),
                str(pptx_path),
            ],
            timeout_s=timeout_s,
        )
        pdf_path = pdf_dir / (pptx_path.stem + ".pdf")
        if not pdf_path.exists():
            raise PptxRenderUnavailable(
                f"soffice did not produce expected PDF at {pdf_path}"
            )

        png_dir = tmpdir / "png"
        png_dir.mkdir()
        prefix = png_dir / "slide"
        _run(
            [
                pdftoppm,
                "-png",
                "-r",
                str(dpi),
                str(pdf_path),
                str(prefix),
            ],
            timeout_s=timeout_s,
        )

        png_paths = sorted(png_dir.glob("slide-*.png"))
        return [p.read_bytes() for p in png_paths]
