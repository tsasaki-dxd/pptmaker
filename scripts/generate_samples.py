"""Generate the static asset gallery shown at /samples.

Reads the catalog from ``scripts.samples_catalog`` and, for each
entry, produces a one-slide .pptx by reusing the DXDesignSystem
template (so samples sit in the real template chrome — title row,
eyebrow, separator, etc.). The body placeholder text is dropped and
replaced with the sample's LayoutSpec shapes; the title text is
rewritten to the sample's ``title``.

Each sample becomes:
  app/web/public/samples/<figure_type>/<id>.png

A manifest read by the Next.js gallery is written to:
  app/web/public/samples/manifest.json

Run via:  python -m scripts.generate_samples
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sys
from pathlib import Path

# Make `app/` importable so render.* resolves the same way pytest does.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "app"))
sys.path.insert(0, str(_REPO_ROOT))

import render.figure_renderers  # noqa: E402, F401  # autoload registry side-effects
from render.figure_renderers.base import EMUBox, RenderContext  # noqa: E402
from render.figure_renderers.registry import REGISTRY as FIGURE_REGISTRY  # noqa: E402
from render.layout_spec import emit_layout_spec  # noqa: E402
from render.media import MediaRegistry  # noqa: E402
from render.pptx_assembler import (  # noqa: E402
    finalize_media,
    read_template_slides,
    rewrite_content_types,
    rewrite_presentation_rels,
    rewrite_presentation_xml,
    write_output_slides,
)
from render.qa.pptx_to_png import render_pptx_to_pngs  # noqa: E402
from render.shapes import DEFAULT_FONT, DEFAULT_PALETTE  # noqa: E402
from render.template_loader import repack, safe_unpack  # noqa: E402
from scripts.samples_catalog import (  # noqa: E402
    BODY_H,
    BODY_W,
    BODY_X,
    BODY_Y,
    SAMPLES,
    Sample,
)

log = logging.getLogger("samples")

TEMPLATE_PATH = _REPO_ROOT / "docs" / "DXDesignSystem_Template.pptx"
OUT_DIR = _REPO_ROOT / "app" / "web" / "public" / "samples"
WORK_DIR = _REPO_ROOT / ".samples_work"
TEMPLATE_SLIDE_INDEX = 4  # the "content" page inside DXDesignSystem


# ------------------------ slide XML mutation -------------------------------


# Body placeholder from the template — full <p:sp ... id="9" ...> ... </p:sp>.
# Stripping it (string match) is cheaper and less error-prone than
# parsing the XML, given the template is fixed.
_BODY_PLACEHOLDER_RE = re.compile(
    r'<p:sp>\s*<p:nvSpPr>\s*<p:cNvPr\s+id="9"[^>]*/>'  # opening of body sp
    r".*?</p:sp>",  # up to its close
    re.DOTALL,
)

# Page indicator (e.g. "04 / 06") — irrelevant for a one-slide sample.
_PAGE_INDICATOR_RE = re.compile(
    r'<p:sp>\s*<p:nvSpPr>\s*<p:cNvPr\s+id="10"[^>]*/>.*?</p:sp>',
    re.DOTALL,
)

# The title text node carrying "コンテンツタイトル". We keep the
# surrounding shape (id=6) intact and only swap the inner <a:t>...</a:t>.
_TITLE_TEXT_RE = re.compile(
    r"<a:t>コンテンツタイトル</a:t>"
)

# Eyebrow text "CONTENT" — replace both occurrences (id=2 + id=5) with
# the figure_type so the gallery clearly tags each sample.
_EYEBROW_TEXT_RE = re.compile(r"<a:t>CONTENT</a:t>")


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _modify_slide(
    slide_xml: str, *, title: str, eyebrow: str, body_shapes: list[str]
) -> str:
    """Take the original template slide XML and produce a sample
    variant. Title text is rewritten, eyebrow text becomes the
    figure_type, the body placeholder is stripped, the page indicator
    is removed, and the LayoutSpec shape XML is appended just before
    </p:spTree>."""
    out = slide_xml
    out = _PAGE_INDICATOR_RE.sub("", out)
    out = _BODY_PLACEHOLDER_RE.sub("", out)
    out = _TITLE_TEXT_RE.sub(
        f"<a:t>{_xml_escape(title)}</a:t>", out, count=1
    )
    out = _EYEBROW_TEXT_RE.sub(
        f"<a:t>{_xml_escape(eyebrow.upper())}</a:t>", out
    )
    blob = "\n".join(body_shapes)
    out = out.replace("</p:spTree>", f"{blob}\n</p:spTree>", 1)
    return out


# ------------------------ rendering ---------------------------------------


def _shapes_for_sample(
    sample: Sample, media: MediaRegistry
) -> list[str]:
    """Produce the shape XML fragments for the body of one sample.

    The MediaRegistry is threaded through so renderers (kpi_dashboard,
    swot, process_flow, business_canvas, icon_list) can register the
    Lucide icon PNGs they emit. ``image_slot`` samples still won't get
    real images because they require a resolved S3 fetch, but
    icon-bearing renderers now light up.
    """
    if sample.spec is not None:
        fragments, _ = emit_layout_spec(sample.spec, media=media)
        return fragments
    if sample.figure_content is None:  # defensive — __post_init__ rules this out
        raise RuntimeError(f"sample {sample.id} has neither spec nor figure_content")
    if sample.figure_type not in FIGURE_REGISTRY:
        raise RuntimeError(
            f"sample {sample.id}: figure_type {sample.figure_type!r} is not registered"
        )
    renderer = FIGURE_REGISTRY[sample.figure_type]
    validation = renderer.validate(sample.figure_content)
    if not validation.ok:
        raise RuntimeError(
            f"sample {sample.id}: figure_content validation failed: {validation.errors}"
        )
    container = EMUBox(x=BODY_X, y=BODY_Y, w=BODY_W, h=BODY_H)
    ctx = RenderContext(
        palette=DEFAULT_PALETTE,
        font=DEFAULT_FONT,
        next_shape_id=2000,
        media=media,
        slide_index=1,
    )
    out = renderer.render(sample.figure_content, container, ctx)
    return list(out.shapes_xml)


def _build_pptx_bytes(work_dir: Path, sample: Sample) -> bytes:
    """Unpack the template, mutate slide{TEMPLATE_SLIDE_INDEX}.xml,
    keep just that one slide, repack."""
    if work_dir.exists():
        shutil.rmtree(work_dir)
    unpacked = safe_unpack(TEMPLATE_PATH, work_dir)

    template_slides = read_template_slides(unpacked.root)
    if TEMPLATE_SLIDE_INDEX not in template_slides:
        raise RuntimeError(
            f"template missing slide{TEMPLATE_SLIDE_INDEX}.xml — adjust constant"
        )
    base = template_slides[TEMPLATE_SLIDE_INDEX]

    media = MediaRegistry()
    fragments = _shapes_for_sample(sample, media)
    new_slide_xml = _modify_slide(
        base.xml,
        title=sample.title,
        eyebrow=sample.figure_type,
        body_shapes=fragments,
    )

    write_output_slides(unpacked.root, [new_slide_xml], [base.rels_xml])
    rewrite_presentation_xml(unpacked.root, slide_count=1)
    rewrite_presentation_rels(unpacked.root, slide_count=1)
    rewrite_content_types(unpacked.root, slide_count=1)

    # Materialize any icon PNGs the renderer registered. Samples never
    # use S3-backed images, so the fetcher always returns None — only
    # inline_bytes (Lucide icons) actually land on disk.
    if media.entries:
        finalize_media(unpacked.root, media, lambda _key: None)

    out_pptx = work_dir.parent / f"_sample_{sample.id}.pptx"
    repack(unpacked, out_pptx)
    data = out_pptx.read_bytes()
    out_pptx.unlink(missing_ok=True)
    return data


def _spec_to_dict(sample: Sample) -> dict[str, object]:
    """Pydantic v2 model_dump — used in manifest for the detail view.
    For figure_renderer samples, returns the content dict directly so
    the gallery shows what fed the renderer."""
    if sample.spec is not None:
        return sample.spec.model_dump(mode="python")
    return {"figure_content": sample.figure_content}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    if not TEMPLATE_PATH.exists():
        log.error("template not found: %s", TEMPLATE_PATH)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, object]] = []
    failures: list[tuple[str, str]] = []

    for i, sample in enumerate(SAMPLES, start=1):
        log.info("[%d/%d] %s (%s)", i, len(SAMPLES), sample.id, sample.figure_type)
        try:
            pptx = _build_pptx_bytes(WORK_DIR / sample.id, sample)
            pngs = render_pptx_to_pngs(pptx, dpi=120, timeout_s=120)
        except Exception as e:
            log.exception("failed: %s", sample.id)
            failures.append((sample.id, str(e)))
            continue
        if not pngs:
            failures.append((sample.id, "no PNG produced"))
            continue
        target_dir = OUT_DIR / sample.figure_type
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{sample.id}.png"
        target_path.write_bytes(pngs[0])
        rel_path = target_path.relative_to(OUT_DIR.parent).as_posix()
        manifest.append(
            {
                "id": sample.id,
                "figure_type": sample.figure_type,
                "title": sample.title,
                "prompt": sample.prompt,
                "notes": sample.notes,
                "image": "/" + rel_path,
                "spec": _spec_to_dict(sample),
            }
        )

    # Sort manifest by figure_type then id for stable diffs.
    manifest.sort(key=lambda m: (m["figure_type"], m["id"]))
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Cleanup workdir but leave outputs.
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR, ignore_errors=True)

    log.info("wrote %d samples to %s", len(manifest), OUT_DIR)
    if failures:
        log.error("failures (%d):", len(failures))
        for sid, err in failures:
            log.error("  %s: %s", sid, err.splitlines()[0])
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
