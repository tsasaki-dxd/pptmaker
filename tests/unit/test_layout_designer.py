"""Layout designer LLM service — exercise both happy-path and
recovery-on-validation-error code paths with a stub Anthropic client
so we don't hit the network."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from render.layout_designer import design_layout, slide_to_designer_dict
from render.layout_spec import LayoutSpec


@dataclass
class _StubBlock:
    text: str
    type: str = "text"


@dataclass
class _StubResponse:
    content: list[_StubBlock]


class _StubLLM:
    """Minimal Anthropic-shaped client: configurable script of replies."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []
        self.messages = self  # so `llm.messages.create(...)` works

    def create(self, **kwargs: Any) -> _StubResponse:
        self.calls.append(kwargs)
        if not self.replies:
            raise RuntimeError("no replies left in stub")
        return _StubResponse(content=[_StubBlock(text=self.replies.pop(0))])


_VALID_SPEC = {
    "slide_index": 4,
    "shapes": [
        {
            "kind": "rect",
            "name": "card-bg",
            "x": 365760,
            "y": 1737360,
            "w": 8412480,
            "h": 1000000,
            "fill": "primary_lt",
            "corner_radius_pct": 8,
        },
        {
            "kind": "text",
            "name": "card-title",
            "x": 500000,
            "y": 1800000,
            "w": 8000000,
            "h": 400000,
            "anchor": "ctr",
            "auto_fit": True,
            "paragraphs": [
                {
                    "align": "ctr",
                    "runs": [
                        {"text": "DX 推進の柱", "size_pt": 18, "bold": True, "color": "primary_dark"}
                    ],
                }
            ],
        },
    ],
}


def test_happy_path_returns_validated_spec() -> None:
    llm = _StubLLM([json.dumps(_VALID_SPEC)])
    spec = design_layout(
        slide={"index": 4, "layout": "content", "content": {"title": "test"}},
        template_page_meta={"layout": "content"},
        body_rect=(365760, 1737360, 8412480, 2834640),
        llm=llm,
    )
    assert isinstance(spec, LayoutSpec)
    assert len(spec.shapes) == 2
    assert len(llm.calls) == 1


def test_retries_then_succeeds_after_validation_error() -> None:
    bad = json.dumps({"slide_index": 1, "shapes": [{"kind": "rect"}]})  # missing required
    llm = _StubLLM([bad, json.dumps(_VALID_SPEC)])
    spec = design_layout(
        slide={"index": 4, "layout": "content"},
        template_page_meta={},
        body_rect=(0, 0, 1000, 1000),
        llm=llm,
        max_retries=2,
    )
    assert isinstance(spec, LayoutSpec)
    assert len(llm.calls) == 2


def test_returns_none_when_all_retries_fail() -> None:
    bad = json.dumps({"slide_index": 1, "shapes": [{"kind": "rect"}]})
    llm = _StubLLM([bad, bad, bad])
    spec = design_layout(
        slide={"index": 4, "layout": "content"},
        template_page_meta={},
        body_rect=(0, 0, 1000, 1000),
        llm=llm,
        max_retries=2,
    )
    assert spec is None
    assert len(llm.calls) == 3


def test_returns_none_when_llm_raises() -> None:
    class Boom:
        messages = None

        def __getattr__(self, _name: str) -> Any:
            raise RuntimeError("api down")

    spec = design_layout(
        slide={"index": 4, "layout": "content"},
        template_page_meta={},
        body_rect=(0, 0, 1000, 1000),
        llm=Boom(),
    )
    assert spec is None


def test_extracts_json_from_code_fence() -> None:
    fenced = f"```json\n{json.dumps(_VALID_SPEC)}\n```"
    llm = _StubLLM([fenced])
    spec = design_layout(
        slide={"index": 4, "layout": "content"},
        template_page_meta={},
        body_rect=(0, 0, 1000, 1000),
        llm=llm,
    )
    assert isinstance(spec, LayoutSpec)


def test_slide_to_designer_dict_drops_unrelated_fields() -> None:
    full = {
        "index": 5,
        "layout": "content",
        "figure_type": "comparison",
        "headline_message": "結論。",
        "content": {"title": "x"},
        "template_slide_index": 4,
        "extra_internal": True,
    }
    out = slide_to_designer_dict(full)
    assert out == {
        "index": 5,
        "layout": "content",
        "figure_type": "comparison",
        "headline_message": "結論。",
        "content": {"title": "x"},
    }


def test_user_prompt_carries_body_rect_and_slide() -> None:
    llm = _StubLLM([json.dumps(_VALID_SPEC)])
    design_layout(
        slide={"index": 4, "layout": "content", "content": {"title": "T"}},
        template_page_meta={"layout": "content"},
        body_rect=(123, 456, 789, 1011),
        llm=llm,
    )
    user_msg = llm.calls[0]["messages"][0]["content"]
    assert "x=123, y=456, w=789, h=1011" in user_msg
    assert "T" in user_msg
