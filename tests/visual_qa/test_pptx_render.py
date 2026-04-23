"""Smoke tests for the real PPTX → PNG pipeline (Phase 2 §8.4)."""

from __future__ import annotations

import io
import shutil

import pytest

from render.qa.pptx_to_png import PptxRenderUnavailable, render_pptx_to_pngs

pytest.importorskip("PIL", reason="Pillow not installed; visual QA skipped.")


def _build_minimal_pptx() -> bytes:
    pptx = pytest.importorskip(
        "pptx", reason="python-pptx not installed; cannot build fixture pptx."
    )
    prs = pptx.Presentation()
    blank_layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[0]
    prs.slides.add_slide(blank_layout)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def test_missing_binaries_raise_pptx_render_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(PptxRenderUnavailable):
        render_pptx_to_pngs(b"not-a-real-pptx")


def test_render_minimal_pptx_smoke() -> None:
    if shutil.which("soffice") is None:
        pytest.skip("soffice not installed; skipping live render smoke test.")
    if shutil.which("pdftoppm") is None:
        pytest.skip("pdftoppm not installed; skipping live render smoke test.")

    pptx_bytes = _build_minimal_pptx()
    pngs = render_pptx_to_pngs(pptx_bytes, dpi=72, timeout_s=90)
    assert len(pngs) == 1
    assert pngs[0].startswith(b"\x89PNG")
