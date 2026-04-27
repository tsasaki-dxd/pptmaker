"""Per-slide layout designer service.

Looks at one blueprint slide + the active template's metadata + the
body container rect, and asks an LLM to return a LayoutSpec — the
structured list of shape primitives to draw inside the body area.

Why this layer exists:
  * The deterministic figure_renderers produce generic boxes-and-bars.
    Goal-quality slides need content-aware composition (HR badges,
    sub-labels, pill annotations, asymmetric column splits, ...) which
    ranges far beyond what a fixed figure_type taxonomy can express.
  * Blueprint already has the content; what's missing is visual
    judgment for THIS particular content on THIS template. LLM is
    uniquely good at that judgment.
  * The renderer stays purely deterministic — the LLM only emits a
    structured spec, validated by Pydantic, and the emitter turns it
    into XML. No LLM-generated XML, no EMU integer landmines, no
    silent-failure shape geometry.

Lives on the render side so it shares the render Lambda's process
with the LayoutSpec emitter and the rest of the deterministic
pipeline; the only external dep is the Anthropic SDK + an API key
fetched from Secrets Manager.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from pydantic import ValidationError

from .layout_spec import LayoutSpec

log = logging.getLogger("slideforge.layout_designer")


_DESIGNER_MODEL_DEFAULT = "claude-sonnet-4-6"
_MAX_RETRIES_DEFAULT = 2


_DESIGNER_PROMPT_TEMPLATE = """\
あなたは PowerPoint スライドのレイアウト設計者です。
ブループリント JSON が与えられた 1 枚のスライドの **本文領域** に何を描くかを、
JSON Schema に従って LayoutSpec として返してください。

【出力形式】
- 出力は LayoutSpec の JSON 1 件のみ（前後に解説や ``` を付けない）。
- shapes は描画順 = 重なり順（先 = 背面、後 = 前面）。
- 座標は EMU。すべてのシェイプは body_area 矩形内に収めること。

【shapes に使えるプリミティブ】
- {{"kind":"rect","name":"...","x":int,"y":int,"w":int,"h":int,
   "fill":"<HEX または palette token>",
   "stroke":"<HEX/token>"|null,"stroke_width_emu":0,"corner_radius_pct":0..50}}
- {{"kind":"text","name":"...","x":int,"y":int,"w":int,"h":int,
   "anchor":"t|ctr|b","auto_fit":true,
   "paragraphs":[{{
     "align":"l|ctr|r|just","indent_level":0..8,
     "bullet":null|"•"|"1.","line_spacing_pct":50..300,
     "space_before_pt":0,"space_after_pt":0,
     "runs":[{{"text":"...","size_pt":4..72,"bold":bool,"italic":bool,
              "underline":bool,"color":"<HEX/token>"}}]
   }}]}}
- {{"kind":"pill","name":"...","x":int,"y":int,"w":int,"h":int,
   "text":"...","fill":"<HEX/token>","text_color":"<HEX/token>","size_pt":int}}
- {{"kind":"line","name":"...","x":int,"y":int,"w":int,"h":int(1〜),
   "color":"<HEX/token>"}}
- {{"kind":"table","name":"...","x":int,"y":int,"w":int,"h":int,
   "rows":[["セル","セル",...], ...],
   // セルは文字列、または以下の CellSpec (混在可)
   //   {{"text":"...","bold":bool|null,"align":"l|ctr|r"|null,
   //     "fill":"<HEX/token>"|null,"text_color":"<HEX/token>"|null,
   //     "col_span":int>=1,"row_span":int>=1}}
   // span を指定したセルが覆う位置にも空セル/CellSpec をそのまま並べてよい
   // (中身は破棄される)。
   "columns":[{{"weight":1.0,"align":"l|ctr|r"}}, ...]|null,
   "column_weights":[1,2,1]|null,  // 簡易版 (columns 未指定時のフォールバック)
   "header":true,"alt_row_bg":false,
   "header_fill":"primary","header_text_color":"white",
   "body_text_color":"text_dark","alt_row_fill":"primary_bg",
   "border_color":"border","font_size_pt":10}}
- {{"kind":"bar_chart","name":"...","x":int,"y":int,"w":int,"h":int,
   // 単系列: items を使う
   "items":[{{"label":"...","value":数値,"color":"<token>"|null}}, ...]|null,
   // 多系列: series + categories を使う (items とは排他)
   "series":[{{"name":"...","values":[v1,v2,...],"color":"<token>"|null}}, ...]|null,
   "categories":["A","B",...]|null,
   "mode":"grouped"|"stacked"|"stacked100",  // 多系列時のレイアウト
   "orientation":"v"|"h","show_values":true,"value_format":"{{:g}}",
   "bar_color":"primary","axis_color":"border","label_color":"muted",
   "value_color":"text_dark","font_size_pt":10}}
- {{"kind":"line_chart","name":"...","x":int,"y":int,"w":int,"h":int,
   "series":[{{"name":"...","values":[v1,v2,...],"color":"<token>"|null}}, ...],
   "x_labels":["Q1","Q2",...]|null,"show_markers":true,
   "axis_color":"border","label_color":"muted","font_size_pt":9}}
- {{"kind":"pie_chart","name":"...","x":int,"y":int,"w":int,"h":int,
   "slices":[{{"label":"...","value":正数,"color":"<token>"|null}}, ...]}}
  ※ pie のラベルは内部に描画されない。必要なら周囲に text/pill を別途配置。

【palette token】
HEX 6 桁の代わりに以下のセマンティック名が使えます:
  primary / primary_dark / primary_lt / primary_bg /
  muted / border / bg_alt / text_dark / text_muted / accent /
  amber / green / black / white

【設計指針】
- タイトルや subtitle / 側面ラベルなどテンプレ固定要素には触らない。
  あなたが描くのは本文領域のみ。
- コンテンツの量と意味に応じて構成を選ぶ:
  * 並列 3〜4 項目 → 横並びカード（roundRect 背景 + アクセント縦バー + JP/EN ラベル + 説明）
  * 比較 / before-after → 2 カラム（背景色を変える / アクセント色で差別化）
  * 工程 / 段階 → 矢印つき横配列、または縦の番号付き
  * 数値強調 → 大きな数字 + ラベル + 補足
  * 表形式データ → table プリミティブ（columns で列幅・整列、CellSpec で
    強調セル / col_span / row_span を表現可能）
  * カテゴリ別の量比較 → bar_chart（単系列は items、多系列は series + categories
    + mode で grouped/stacked/stacked100）
  * 時系列の推移 → line_chart（series で複数本、x_labels で軸ラベル）
  * 構成比 → pie_chart（slices）。ラベルは内部に出ないので必要なら周囲に pill
- 余白を取る（ラベルと値、カードとカード間）。
- フォントサイズは情報階層を反映: タイトル 14-18pt, ラベル 9-11pt, 本文 10-12pt, 注記 8-9pt。
- 色は palette token を優先（HEX 直書きは特別な強調色のみ）。
- N 個の要素を等分配置するときは座標計算で隙間を均等に。

【ブループリントスライド】
{slide_json}

【テンプレページ情報】
{template_page_json}

【本文領域 (この内側に収めること)】
x={body_x}, y={body_y}, w={body_w}, h={body_h}

【出力】
"""


def _designer_enabled() -> bool:
    return os.environ.get("FF_LAYOUT_DESIGNER", "0") == "1"


def _designer_model() -> str:
    return os.environ.get("CLAUDE_MODEL_LAYOUT_DESIGNER", _DESIGNER_MODEL_DEFAULT)


def _extract_json(text: str) -> Any:
    """Best-effort JSON extraction. Accepts bare JSON, JSON inside a
    ```json fence, or a leading prose paragraph followed by JSON."""
    s = text.strip()
    if s.startswith("```"):
        # ```json ... ``` or ``` ... ```
        m = re.search(r"```(?:json)?\s*\n(.*?)\n```", s, re.DOTALL)
        if m:
            s = m.group(1).strip()
    return json.loads(s)


def slide_to_designer_dict(slide: dict[str, Any]) -> dict[str, Any]:
    """Project the blueprint slide down to the fields the designer
    needs (drops noise that wastes input tokens)."""
    return {
        "index": slide.get("index"),
        "layout": slide.get("layout"),
        "figure_type": slide.get("figure_type"),
        "headline_message": slide.get("headline_message"),
        "content": slide.get("content", {}),
    }


def _bounds_violations(
    spec: LayoutSpec, body_rect: tuple[int, int, int, int]
) -> list[str]:
    """Return human-readable strings for every shape that lies outside
    the body container. Empty list = clean.

    The Pydantic schema only enforces non-negative coords, not the
    body_rect bound, so we check it here and feed any violation back
    into the retry loop so the LLM can correct itself.
    """
    bx, by, bw, bh = body_rect
    bx_max = bx + bw
    by_max = by + bh
    out: list[str] = []
    for shape in spec.shapes:
        x = getattr(shape, "x", None)
        y = getattr(shape, "y", None)
        w = getattr(shape, "w", None)
        h = getattr(shape, "h", None)
        if x is None or y is None or w is None or h is None:
            continue
        if x < bx or y < by or x + w > bx_max or y + h > by_max:
            out.append(
                f"shape '{getattr(shape, 'name', shape.kind)}' (kind={shape.kind}) "
                f"at x={x},y={y},w={w},h={h} は body_area "
                f"x={bx}..{bx_max}, y={by}..{by_max} を逸脱"
            )
    return out


def design_layout(
    *,
    slide: dict[str, Any],
    template_page_meta: dict[str, Any],
    body_rect: tuple[int, int, int, int],
    llm: Any,
    max_retries: int = _MAX_RETRIES_DEFAULT,
) -> LayoutSpec | None:
    """Ask the LLM to design the body of one slide.

    Returns a validated LayoutSpec, or ``None`` on failure (caller
    falls back to deterministic figure rendering).

    `llm` must expose ``messages.create(...)`` matching the Anthropic
    SDK shape so unit tests can substitute a stub.
    """
    body_x, body_y, body_w, body_h = body_rect
    base_prompt = _DESIGNER_PROMPT_TEMPLATE.format(
        slide_json=json.dumps(slide_to_designer_dict(slide), ensure_ascii=False, indent=2),
        template_page_json=json.dumps(template_page_meta, ensure_ascii=False, indent=2),
        body_x=body_x,
        body_y=body_y,
        body_w=body_w,
        body_h=body_h,
    )

    last_error: str | None = None
    for attempt in range(max_retries + 1):
        prompt = base_prompt
        if last_error:
            prompt += (
                f"\n\n直前の試行はバリデーションエラー: {last_error}\n"
                "上のスキーマに合わせて修正版を返してください。"
            )
        try:
            resp = llm.messages.create(
                model=_designer_model(),
                max_tokens=4096,
                temperature=0.3,
                system=(
                    "You are a precise PPTX layout designer. Output JSON only — "
                    "no commentary, no code fence."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(
                b.text for b in resp.content if getattr(b, "type", None) == "text"
            )
            data = _extract_json(text)
            spec = LayoutSpec.model_validate(data)
            violations = _bounds_violations(spec, body_rect)
            if violations:
                # Treat as a retryable validation error so the LLM gets
                # the offending shape list and a chance to fix.
                last_error = (
                    "body_area 越境: " + "; ".join(violations[:5])
                )[:600]
                log.warning(
                    "layout designer bounds violation (attempt %d): %s",
                    attempt + 1,
                    last_error,
                )
                continue
            return spec
        except ValidationError as e:
            last_error = str(e)[:600]
            log.warning(
                "layout designer validation failed (attempt %d): %s",
                attempt + 1,
                last_error,
            )
        except Exception:
            log.exception(
                "layout designer LLM call failed (attempt %d)", attempt + 1
            )
            return None

    log.warning(
        "layout designer giving up after %d attempts; falling back",
        max_retries + 1,
    )
    return None
