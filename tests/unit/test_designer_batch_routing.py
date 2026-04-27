"""Designer batch routing — content slides hit the LLM, structural
pages (cover / toc / section_divider / about / disclaimer) skip it.
Regression guard so a future template JSON edit that accidentally
adds body_box to the wrong page entry can't start burning LLM cost
on the wrong layouts."""

from __future__ import annotations

from typing import Any, ClassVar

from render.handler import _collect_designer_result, _submit_designer_batch
from render.template_meta import load_template_meta


class _SentinelLLM:
    """Stub that counts how many times design_layout would hit it
    indirectly via executor.submit(design_layout, ...)."""

    def __init__(self) -> None:
        self.create_calls = 0
        self.messages = self

    def create(self, **_: Any) -> Any:
        self.create_calls += 1
        # Return a minimally-valid LayoutSpec so validation passes.
        # Coordinates must sit inside the dxdesignsystem template's
        # content body_box (~ x=365760..8778240, y=1737360..4572000)
        # or the bounds-validation retry will reject the spec.
        class _Block:
            type = "text"
            text = (
                '{"slide_index": 1, "shapes": [{"kind":"rect","name":"x",'
                '"x":400000,"y":2000000,"w":1000,"h":1000,"fill":"primary"}]}'
            )

        class _Resp:
            content: ClassVar[list[Any]] = [_Block()]

        return _Resp()


def _blueprint_with(layouts: list[str]) -> list[dict[str, Any]]:
    return [
        {"index": i + 1, "layout": layout, "figure_type": None, "content": {"title": f"t{i}"}}
        for i, layout in enumerate(layouts)
    ]


def test_only_content_slides_route_through_designer() -> None:
    meta = load_template_meta("dxdesignsystem")
    assert meta is not None
    llm = _SentinelLLM()

    slides = _blueprint_with([
        "cover", "toc", "section_divider", "content",
        "content", "about", "disclaimer",
    ])
    futures = _submit_designer_batch(
        blueprint_slides=slides, template_meta=meta, designer_llm=llm
    )

    # Every slide gets an entry (either real future or pre-resolved None).
    assert set(futures.keys()) == set(range(1, len(slides) + 1))

    # Block on all futures so the thread pool's designer calls complete
    # before we count.
    resolved = {i: _collect_designer_result(futures, i) for i in futures}

    # Only the two content slides produced a non-None LayoutSpec.
    assert resolved[1] is None  # cover
    assert resolved[2] is None  # toc
    assert resolved[3] is None  # section_divider
    assert resolved[4] is not None  # content
    assert resolved[5] is not None  # content
    assert resolved[6] is None  # about
    assert resolved[7] is None  # disclaimer

    # And the LLM stub got hit exactly twice.
    assert llm.create_calls == 2


def test_no_designer_llm_returns_empty_futures() -> None:
    meta = load_template_meta("dxdesignsystem")
    futures = _submit_designer_batch(
        blueprint_slides=_blueprint_with(["content", "content"]),
        template_meta=meta,
        designer_llm=None,
    )
    assert futures == {}


def test_no_template_meta_returns_empty_futures() -> None:
    llm = _SentinelLLM()
    futures = _submit_designer_batch(
        blueprint_slides=_blueprint_with(["content"]),
        template_meta=None,
        designer_llm=llm,
    )
    assert futures == {}
    assert llm.create_calls == 0
