"""Convert .pptx to per-slide JPEG previews via LibreOffice + pdftoppm."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger("slideforge.render.preview")

# Lambda's $HOME is on a read-only filesystem, so LibreOffice's default
# user-profile path (~/.config/libreoffice) can't be created and it
# exits with:
#   Fatal Error: The application cannot be started.
#   User installation could not be completed.
# Redirect the profile to /tmp (writable). Kept at a stable location
# so a warm container reuses the profile instead of reinitialising on
# every render.
_LO_PROFILE_DIR = "file:///tmp/lo-profile"


def _run(cmd: list[str]) -> None:
    """subprocess.run with check=True, but surface stdout/stderr in the
    CalledProcessError message. The default CalledProcessError str() only
    shows the return code, which makes "soffice failed" log lines
    completely useless for diagnosis."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log.error(
            "command failed: %s\n--- stdout ---\n%s\n--- stderr ---\n%s",
            " ".join(cmd),
            proc.stdout,
            proc.stderr,
        )
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=proc.stdout, stderr=proc.stderr
        )


def pptx_to_pdf(pptx_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "soffice",
            "--headless",
            f"-env:UserInstallation={_LO_PROFILE_DIR}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(pptx_path),
        ]
    )
    return out_dir / (pptx_path.stem + ".pdf")


def pdf_to_jpegs(pdf_path: Path, out_dir: Path, dpi: int = 110) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "slide"
    _run(
        [
            "pdftoppm",
            "-jpeg",
            "-r",
            str(dpi),
            str(pdf_path),
            str(prefix),
        ]
    )
    return sorted(out_dir.glob("slide-*.jpg"))


def pptx_to_jpegs(pptx_path: Path, workdir: Path, dpi: int = 110) -> list[Path]:
    pdf = pptx_to_pdf(pptx_path, workdir)
    return pdf_to_jpegs(pdf, workdir / "jpeg", dpi=dpi)
