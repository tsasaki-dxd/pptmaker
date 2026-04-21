"""Template unpack safety tests."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from render.template_loader import TemplateError, repack, safe_unpack


def _make_pptx(tmp: Path, members: dict[str, bytes]) -> Path:
    p = tmp / "t.pptx"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    p.write_bytes(buf.getvalue())
    return p


def test_unpack_minimal(tmp_path: Path) -> None:
    pptx = _make_pptx(
        tmp_path,
        {
            "[Content_Types].xml": b"<x/>",
            "ppt/slides/slide1.xml": b"<s/>",
        },
    )
    unpacked = safe_unpack(pptx, tmp_path / "out")
    assert unpacked.slide_path(1).exists()


def test_zip_slip_blocked(tmp_path: Path) -> None:
    # Craft a zip with a parent-escape name
    bad = tmp_path / "bad.pptx"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../evil.xml", b"hi")
    with pytest.raises(TemplateError):
        safe_unpack(bad, tmp_path / "out2")


def test_too_many_entries_blocked(tmp_path: Path) -> None:
    bad = tmp_path / "many.pptx"
    with zipfile.ZipFile(bad, "w") as zf:
        for i in range(3000):
            zf.writestr(f"f{i}", b"x")
    with pytest.raises(TemplateError):
        safe_unpack(bad, tmp_path / "out3")


def test_repack_roundtrip(tmp_path: Path) -> None:
    pptx = _make_pptx(
        tmp_path,
        {
            "[Content_Types].xml": b"<x/>",
            "ppt/slides/slide1.xml": b"<s/>",
        },
    )
    unpacked = safe_unpack(pptx, tmp_path / "u")
    out = repack(unpacked, tmp_path / "out.pptx")
    assert out.exists()
    with zipfile.ZipFile(out) as zf:
        assert "ppt/slides/slide1.xml" in zf.namelist()
