# Visual QA workflow (L3 golden-file checks)

Phase 2 design §8.4 defines an optional rendering-quality gate: assemble a
PPTX, rasterise each slide to PNG, and compare against a committed golden
image using SSIM. This doc covers day-to-day use of the scaffold.

## Layout

```
tests/visual_qa/
  conftest.py                 # --update-golden option + fixture
  test_visual_diff_helper.py  # smoke tests for the SSIM helper
  golden/<case>/slide_<N>.png # committed golden assets (one dir per case)
```

`app/render/qa/visual_diff.py` exposes `compute_ssim` and `images_differ`.

## Adding a new golden case

1. Pick a slug for the case (e.g. `bullet_list_basic`) and create
   `tests/visual_qa/golden/<case>/`.
2. Add a pytest module under `tests/visual_qa/` that builds the PPTX,
   rasterises each slide, and compares against
   `golden/<case>/slide_<N>.png` via `compute_ssim(...) >= 0.98`.
3. Run with `--update-golden` to populate the PNGs on first commit.

## Refreshing goldens

```bash
pytest tests/visual_qa/ --update-golden
```

Review the resulting PNG diffs in your PR; never blind-commit updates.

## CI guidance (§8.5)

L3 is heavyweight (LibreOffice + `pdftoppm`), so it does **not** run on
every PR. Trigger it via the `visual-qa` label or the nightly workflow.
The default `pytest` invocation picks up `tests/visual_qa/` but the helper
tests skip cleanly when Pillow is missing.

## Dependencies

- **Pillow** — required for the SSIM helper (`pip install Pillow`).
- **LibreOffice** + **`pdftoppm`** (from `poppler-utils`) — required for
  the real PPTX → PNG pipeline. Not scaffolded in this round; add a
  renderer module alongside the first real golden case.
