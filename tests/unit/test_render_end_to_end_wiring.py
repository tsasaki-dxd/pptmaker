"""End-to-end wiring of ``slots`` and ``theme_pptx_bytes`` through the
render Lambda entry point.

These tests confirm that ``app/render/handler.py::_process_job`` looks up
the TemplateProfile layout by ``template_slide_index`` and forwards both
``slots`` (from the layout entry) and ``theme_pptx_bytes`` (the downloaded
template bytes, ONCE per job) to ``render_content_slide``. All heavy I/O
is monkeypatched — no real S3, no zip repack, no LibreOffice.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from render import handler as render_handler

_TEMPLATE_BYTES = b"FAKE_PPTX_TEMPLATE_BYTES"


def _build_job(
    layouts: list[dict[str, Any]],
    blueprint_slides: list[dict[str, Any]] | None = None,
) -> render_handler.RenderJob:
    return render_handler.RenderJob(
        job_id="job-1",
        tenant_id="t1",
        project_id="p1",
        template_s3="s3://bucket/tenants/t1/templates/abc.pptx",
        blueprint={
            "title": "T",
            "slides": blueprint_slides
            or [
                {
                    "index": 1,
                    "layout": "content",
                    "figure_type": None,
                    "content": {"title": "Slide 1"},
                    "template_slide_index": 1,
                }
            ],
        },
        out_prefix="s3://bucket/out/v1/",
        template_layouts=layouts,
    )


@pytest.fixture
def stub_pipeline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, Any]:
    """Stub every side-effecting step in ``_process_job`` except
    ``render_content_slide``. Captures kwargs passed to the renderer."""

    calls: list[dict[str, Any]] = []
    template_bytes_holder: dict[str, bytes | None] = {"value": _TEMPLATE_BYTES}

    def fake_download(_uri: str, dest: Path) -> None:
        body = template_bytes_holder["value"]
        if body is None:
            # Produce an empty file so _read_template_bytes still works;
            # the test that wants "None bytes" patches _read_template_bytes
            # directly instead.
            dest.write_bytes(b"")
        else:
            dest.write_bytes(body)

    class _StubUnpacked:
        def __init__(self, root: Path) -> None:
            self.root = root

    def fake_safe_unpack(_pptx: Path, out: Path) -> _StubUnpacked:
        out.mkdir(parents=True, exist_ok=True)
        return _StubUnpacked(out)

    def fake_read_template_slides(_root: Path) -> dict[int, SimpleNamespace]:
        # Return 2 template slides so blueprint slides can map to 1 or 2.
        return {
            1: SimpleNamespace(xml="<p:sld>one</p:sld>", rels_xml=None),
            2: SimpleNamespace(xml="<p:sld>two</p:sld>", rels_xml=None),
        }

    def fake_render_content_slide(
        slide_xml: str, req: Any, **kwargs: Any
    ) -> str:
        calls.append(
            {
                "slide_xml": slide_xml,
                "req": req,
                "kwargs": kwargs,
            }
        )
        return slide_xml

    def noop(*_a: Any, **_kw: Any) -> Any:
        return None

    def fake_finalize_media(*_a: Any, **_kw: Any) -> list[str]:
        return []

    def fake_repack(_unpacked: Any, out: Path) -> None:
        out.write_bytes(b"OUT")

    def fake_pptx_to_pdf(*_a: Any, **_kw: Any) -> Path:
        raise RuntimeError("preview disabled in test")

    monkeypatch.setattr(render_handler, "_download", fake_download)
    monkeypatch.setattr(render_handler, "safe_unpack", fake_safe_unpack)
    monkeypatch.setattr(
        render_handler, "read_template_slides", fake_read_template_slides
    )
    monkeypatch.setattr(render_handler, "render_content_slide", fake_render_content_slide)
    monkeypatch.setattr(render_handler, "write_output_slides", noop)
    monkeypatch.setattr(render_handler, "rewrite_presentation_xml", noop)
    monkeypatch.setattr(render_handler, "rewrite_presentation_rels", noop)
    monkeypatch.setattr(render_handler, "rewrite_content_types", noop)
    monkeypatch.setattr(render_handler, "finalize_media", fake_finalize_media)
    monkeypatch.setattr(render_handler, "repack", fake_repack)
    monkeypatch.setattr(render_handler, "pptx_to_pdf", fake_pptx_to_pdf)
    monkeypatch.setattr(render_handler, "_upload", noop)

    return {"calls": calls, "template_bytes": template_bytes_holder}


def test_slots_and_theme_bytes_forwarded_to_renderer(
    stub_pipeline: dict[str, Any],
) -> None:
    layouts = [
        {
            "index": 1,
            "layout": "content",
            "slots": [
                {"id": "body_main", "kind": "figure", "x": 0, "y": 0, "w": 100, "h": 100}
            ],
            "fixed_elements": [],
        }
    ]
    job = _build_job(layouts)
    render_handler._process_job(job)

    calls = stub_pipeline["calls"]
    assert len(calls) == 1
    kwargs = calls[0]["kwargs"]
    assert kwargs["slots"] == layouts[0]["slots"]
    assert kwargs["theme_pptx_bytes"] == _TEMPLATE_BYTES


def test_no_template_bytes_passes_none(
    stub_pipeline: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force _read_template_bytes to return None regardless of the
    # (empty) file the stubbed downloader wrote.
    monkeypatch.setattr(render_handler, "_read_template_bytes", lambda _p: None)

    layouts = [
        {
            "index": 1,
            "layout": "content",
            "slots": [
                {"id": "body_main", "kind": "figure", "x": 0, "y": 0, "w": 10, "h": 10}
            ],
            "fixed_elements": [],
        }
    ]
    job = _build_job(layouts)
    render_handler._process_job(job)

    calls = stub_pipeline["calls"]
    assert len(calls) == 1
    kwargs = calls[0]["kwargs"]
    assert kwargs["theme_pptx_bytes"] is None
    assert kwargs["slots"] == layouts[0]["slots"]


def test_layout_without_slots_key_yields_empty_list(
    stub_pipeline: dict[str, Any],
) -> None:
    layouts = [
        {"index": 1, "layout": "content"}  # no "slots" key at all
    ]
    job = _build_job(layouts)
    render_handler._process_job(job)

    calls = stub_pipeline["calls"]
    assert len(calls) == 1
    kwargs = calls[0]["kwargs"]
    assert kwargs["slots"] == []
    assert kwargs["slots"] is not None
    assert kwargs["theme_pptx_bytes"] == _TEMPLATE_BYTES


def test_template_bytes_downloaded_once_across_slides(
    stub_pipeline: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    read_calls: list[Path] = []
    real_read = render_handler._read_template_bytes

    def counting_read(path: Path) -> bytes | None:
        read_calls.append(path)
        return real_read(path)

    monkeypatch.setattr(render_handler, "_read_template_bytes", counting_read)

    layouts = [
        {
            "index": 1,
            "layout": "content",
            "slots": [
                {"id": "a", "kind": "figure", "x": 0, "y": 0, "w": 1, "h": 1}
            ],
            "fixed_elements": [],
        },
        {
            "index": 2,
            "layout": "content",
            "slots": [
                {"id": "b", "kind": "figure", "x": 0, "y": 0, "w": 2, "h": 2}
            ],
            "fixed_elements": [],
        },
    ]
    job = _build_job(
        layouts,
        blueprint_slides=[
            {
                "index": 1,
                "layout": "content",
                "figure_type": None,
                "content": {"title": "A"},
                "template_slide_index": 1,
            },
            {
                "index": 2,
                "layout": "content",
                "figure_type": None,
                "content": {"title": "B"},
                "template_slide_index": 2,
            },
        ],
    )

    render_handler._process_job(job)

    assert len(read_calls) == 1
    calls = stub_pipeline["calls"]
    assert len(calls) == 2
    assert calls[0]["kwargs"]["slots"] == layouts[0]["slots"]
    assert calls[1]["kwargs"]["slots"] == layouts[1]["slots"]
    # Both slides share the same template bytes object (one download).
    assert (
        calls[0]["kwargs"]["theme_pptx_bytes"]
        is calls[1]["kwargs"]["theme_pptx_bytes"]
    )
