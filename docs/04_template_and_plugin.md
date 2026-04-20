# 04. テンプレート解析・図表プラグイン設計書

**文書名**：SlideForge 詳細設計 — Template Registry / Render Engine / Figure Plugin
**版**：Draft v0.1
**参照**：`SlideForge_概要設計書.md` §4.1 / §4.3、`scripts/shape_lib.py`, `scripts/build_figures_part*.py`, `scripts/normalize_template.py`

---

## 1. 目的とスコープ

テンプレート (.pptx) をプロファイル化する仕組みと、Blueprint から .pptx を組み上げる Render Engine、新規図表タイプを追加可能にする図表プラグイン IF を設計する。

関連モジュール責務：

| モジュール | 責務 |
|---|---|
| Template Registry | .pptx の解凍・解析・分類・プロファイル化 |
| Template Normalizer | フォント / 色の正規化（PoC の `normalize_template.py` 後継） |
| Blueprint Builder | (別書 01) |
| Render Engine | TemplateProfile + Blueprint → .pptx |
| Figure Plugin Registry | 図表タイプの登録・検索・バリデーション |

---

## 2. テンプレートプロファイル詳細スキーマ

```yaml
# TemplateProfile v1.0
id: "tp_0001"
version: "1.0"
name: "DXデザインシステム v1"
tenant_id: "t_001"
original_s3_path: "s3://.../tenants/t_001/templates/tp_0001/original.pptx"
normalized_s3_path: "s3://.../tenants/t_001/templates/tp_0001/normalized.pptx"
created_at: "2026-04-16T10:00:00+09:00"

slide_size:
  cx_emu: 12192000   # 16:9 13.333in
  cy_emu: 6858000    # 7.5in

design_tokens:
  colors:
    primary:    "#8B7AB8"
    primary_lt: "#D9D1E8"
    primary_dk: "#6B5C96"
    primary_bg: "#F5F2F9"
    text:       "#3A3A42"
    text_sub:   "#5E5C6A"
    text_muted: "#9B98A6"
    border:     "#E8E6EC"
    bg_alt:     "#FAFAFB"
    accent_a:   "#C4A05C"
    accent_b:   "#5E9B7F"
  fonts:
    heading: { family: "Noto Sans JP", weight: 700 }
    body:    { family: "Noto Sans JP", weight: 400 }
    mono:    { family: "Consolas",     weight: 400 }
  spacing:
    gutter_emu: 228600   # 0.25in
    margin_x_emu: 914400

layouts:
  - id: "cover"
    source_slide_index: 1
    placeholders:
      - { role: "title",    x: 914400,  y: 2286000, cx: 10287000, cy: 1371600 }
      - { role: "subtitle", x: 914400,  y: 3657600, cx: 10287000, cy: 762000  }
      - { role: "date",     x: 914400,  y: 5943600, cx: 3657600,  cy: 457200  }
    fixed_elements:
      - { type: "logo", x: 10287000, y: 457200, cx: 990600, cy: 457200 }
  - id: "toc"
    source_slide_index: 2
    placeholders:
      - { role: "items", type: "list", max_items: 8 }
  - id: "section_divider"
    source_slide_index: 3
    placeholders:
      - { role: "number" }
      - { role: "title" }
      - { role: "description" }
  - id: "content"
    source_slide_index: 4
    placeholders:
      - { role: "title" }
      - { role: "body_area", x: 457200, y: 1524000, cx: 11277600, cy: 4953000 }
  - id: "about"
    source_slide_index: 17
    placeholders: [...]
  - id: "disclaimer"
    source_slide_index: 18
    placeholders: [...]

validation:
  warnings:
    - "slide 5 に分類信頼度 52% のレイアウトあり。ユーザー確認要"
```

---

## 3. レイアウト自動分類

### 3.1 アプローチ比較

| 方式 | 精度 | コスト | 保守性 |
|---|---|---|---|
| A. ルールベース | 高（典型パターン） | 低 | 高 |
| B. LLM 分類 | 中〜高 | 中 | 中 |
| C. 併用 | 高（不明のみLLM） | 低〜中 | 高 |

**採用：C. ルールベース + LLM フォールバック**

### 3.2 ルール（信頼度 0.0〜1.0）

| レイアウト | 判定ルール | 信頼度 |
|---|---|---|
| cover | 最初のスライド かつ タイトル＋サブタイトル＋日付プレースホルダ | 0.95 |
| toc | 箇条書き 5 件以上 かつ 番号付き かつ タイトルが「目次」等 | 0.90 |
| section_divider | 大型番号（二桁）＋短いタイトル かつ 本文エリア空 | 0.85 |
| content | `body_area` 大型プレースホルダあり | 0.70 |
| about | タイトルに「会社概要/About/Company」 | 0.90 |
| disclaimer | タイトルに「免責/Disclaimer」 または 最終スライド | 0.80 |

### 3.3 LLM フォールバック

ルールで信頼度 < 0.65 の場合のみ Haiku 4.5 に問い合わせ：

```
入力: スライドの XML 要約（タイトル文、プレースホルダー数、位置、ロゴ有無）
出力: {"layout": "content", "confidence": 0.72, "reason": "..."}
```

### 3.4 ユーザー確認 UI

信頼度 < 0.8 のスライドは確認アイコン付きで表示、ユーザー上書き可能。確定後は TemplateProfile に反映し、以降そのテンプレで同じ判定が出ても自動で確定値を採用する学習ログを保持。

### 3.5 精度目標

初期目標：分類 Top-1 精度 90%。社内 20 テンプレで計測し、低精度のルールを改善。

---

## 4. テンプレート正規化ポリシー

PoC の `normalize_template.py` は「Yu Gothic → Noto Sans JP / 濃紫 → 柔らかい紫」を決め打ちで置換していた。本番では次の二段構え：

### 4.1 自動正規化（デフォルト ON）

- **フォント**: テンプレ中の未インストールフォント → Noto Sans JP にフォールバック警告
- **行間 / 字間**: 明らかに不適切な値のみ補正
- **EMU 値の整数化**: 既存テンプレにも適用（PoC 教訓）

### 4.2 提案のみ（デフォルト OFF）

- **配色**: WCAG コントラスト不足の組み合わせを提案
- **フォント統一**: 見出し/本文の不統一を提案

### 4.3 原則

- テンプレ提供者の意図を壊さない
- 正規化前/後の両方を保持（rollback 可能）
- 適用箇所は `normalization_log` としてプロファイルに残す

---

## 5. プレースホルダ抽出仕様

.pptx 解凍後、`ppt/slides/slide*.xml` を走査：

- `<p:sp>` 要素を抽出
- `<p:nvSpPr>/<p:nvPr>/<p:ph>` の `type` と `idx` からプレースホルダ種別推定
- `<p:spPr>/<a:xfrm>/<a:off>` `<a:ext>` から座標・サイズ（EMU）取得
- 固定要素（ロゴ、装飾図形）は `<p:ph>` を持たない `<p:sp>` / `<p:pic>` として別扱い

```python
@dataclass
class Placeholder:
    role: str              # title / subtitle / body_area / ...
    type: str              # text / list / picture / table
    x: int; y: int; cx: int; cy: int  # EMU、必ず int
    idx: int | None = None
```

---

## 6. Render Engine 内部構造

```
Blueprint + TemplateProfile
        │
        ▼
┌────────────────────┐
│ TemplateLoader     │  .pptx 解凍、ベーススライドセット作成
└────────────────────┘
        │
        ▼
┌────────────────────┐
│ LayoutRenderer     │  各 slide に対し layout 種別で分岐
│  - CoverRenderer   │
│  - TocRenderer     │
│  - SectionRenderer │
│  - ContentRenderer ├─► FigureRenderer (plugin)
│  - AboutRenderer   │
│  - DisclaimerR.    │
└────────────────────┘
        │
        ▼
┌────────────────────┐
│ ShapeXMLEmitter    │  EMU 整数化ガード付き
└────────────────────┘
        │
        ▼
┌────────────────────┐
│ Packer             │  ppt/presentation.xml 整合、.pptx ZIP
└────────────────────┘
        │
        ▼
     .pptx ファイル
```

---

## 7. 図表プラグイン IF

### 7.1 ABC 定義

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class EMURect:
    x: int; y: int; cx: int; cy: int
    def __post_init__(self):
        for v in (self.x, self.y, self.cx, self.cy):
            assert isinstance(v, int), "EMU must be int (PoC lesson)"

@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]

@dataclass
class ShapeXML:
    sp_id: int
    xml: str  # <p:sp>...</p:sp>

class FigureRenderer(ABC):
    """図表プラグインが実装する抽象 IF"""

    figure_type: str          # e.g. "table"
    description: str          # LLM に提示する説明
    input_schema: dict        # JSON Schema
    preview_example: dict     # LLM Few-shot 用の最小例

    @abstractmethod
    def validate_content(self, content: dict) -> ValidationResult: ...

    @abstractmethod
    def estimate_area(self, content: dict, container: EMURect) -> EMURect:
        """実際に必要な領域を返す（container 以内）"""

    @abstractmethod
    def render(self, content: dict, container: EMURect,
               tokens: "DesignTokens") -> list[ShapeXML]: ...
```

### 7.2 登録機構

```python
# slideforge/figures/registry.py
_REGISTRY: dict[str, type[FigureRenderer]] = {}

def register(cls: type[FigureRenderer]) -> type[FigureRenderer]:
    _REGISTRY[cls.figure_type] = cls
    return cls

def get(figure_type: str) -> FigureRenderer:
    return _REGISTRY[figure_type]()

def catalog() -> list[dict]:
    return [
        {"type": cls.figure_type,
         "description": cls.description,
         "schema": cls.input_schema,
         "example": cls.preview_example}
        for cls in _REGISTRY.values()
    ]
```

- 標準プラグイン: `slideforge.figures.builtin.*` で `@register` デコレータ
- 外部プラグイン: Python entry points (`slideforge.figures`) で外部パッケージから拡張可

### 7.3 テナント独自プラグイン

- 信頼テナントのみ有効化（管理画面でホワイトリスト）
- Python コード実行になるため、本番は `figure_type: "custom_xxx"` を受け取って、別コンテナ（サンドボックス）で実行するアーキテクチャを Phase 3 で検討
- Phase 1/2 は標準プラグインのみ

---

## 8. 標準図表タイプ一覧

PoC の 10 種を踏襲。各タイプの input schema を YAML で定義（抜粋）。

### 8.1 `table`

```yaml
type: object
required: [headers, rows]
properties:
  headers: { type: array, items: { type: string }, minItems: 1, maxItems: 8 }
  rows:
    type: array
    items: { type: array, items: { type: string } }
  accent_col: { type: integer, default: 0 }  # 強調する列
```

### 8.2 `cards_grid`

```yaml
type: object
required: [cards]
properties:
  cards:
    type: array
    items:
      type: object
      required: [title, body]
      properties:
        title: string
        body: string
        badge: string
  columns: { type: integer, enum: [2,3,4], default: 3 }
```

### 8.3 `two_column`

```yaml
required: [left, right]
properties:
  left:  { type: object, properties: { title: string, items: array } }
  right: { type: object, properties: { title: string, items: array } }
  footer_box: { type: object }  # 費用等
```

### 8.4 `timeline`

```yaml
required: [steps]
properties:
  steps:
    type: array
    minItems: 2
    maxItems: 8
    items: { required: [label, period], ... }
  orientation: { enum: [horizontal, vertical], default: horizontal }
```

### 8.5 `stat_callout` / `bullet_list` / `process_flow` / `comparison` / `stack_bar` / `cost_breakdown`

いずれも PoC の `build_figures_part*.py` の実装を抽出し、同様の構造で定義。スキーマは各ファイルから逆引きで起こす（Phase 0 の作業項目）。

---

## 9. EMU 座標と整数化ガード

PoC で最もつまずいた箇所。型レベルで防ぐ：

```python
class EMU(int):
    """EMU 単位の整数型。float 代入を拒否。"""
    def __new__(cls, v):
        if isinstance(v, float):
            raise TypeError("EMU must be int, got float")
        return super().__new__(cls, int(v))

def emu_inches(inch: float) -> EMU:
    return EMU(round(inch * 914400))

def emu_points(pt: float) -> EMU:
    return EMU(round(pt * 12700))
```

- 全ての `FigureRenderer.render` の返す XML で EMU 値は `EMU` 型を通す
- `ShapeXMLEmitter` が最終的に `str(int(emu))` で埋め込む

---

## 10. shape_lib → システム化リファクタリング

### 10.1 現状（PoC）

- `scripts/shape_lib.py` がフリー関数（`rect_shape`, `text_box`, `pill_label` 等）
- 図表ごとの `build_figures_part*.py` がそれらを手続的に呼ぶ
- テンプレートパスやスライド番号がハードコード

### 10.2 リファクタリング方針

| Before | After |
|---|---|
| `shape_lib.py` 関数群 | `slideforge/render/shapes/` モジュール、`Shape` データクラス経由 |
| `_i()` ヘルパ | `EMU` 型で保証 |
| ハードコードスライド番号 | TemplateProfile.layouts 参照 |
| `build_figures_part*.py` | `slideforge/figures/builtin/{table,cards_grid,...}.py` に分割 |
| `normalize_template.py` | `slideforge/template_registry/normalizer.py` + 設定駆動 |

### 10.3 移行ステップ

1. 既存 PoC コードを `legacy/` に退避
2. 新構造で `table` のみ実装、テストで旧出力と pixel diff 0
3. 順次 `cards_grid` → `two_column` → … と置換
4. 既存のバイナリ互換を E2E で担保

---

## 11. 図表の自動選定ロジック

Blueprint Builder（LLM）が figure_type を選ぶ際の入力として、本モジュールは Registry から以下を供給：

```python
# LLM に渡すカタログ（Prompt Caching 対象）
registry.catalog()
# => [
#   {"type":"table","description":"多列の比較表。行数5〜20、列数2〜8推奨。",...},
#   {"type":"cards_grid","description":"概念を並列に示す。3列×2行まで。",...},
#   ...
# ]
```

LLM 選定の妥当性評価（01_prompt_engineering.md §11 の Eval と連携）はこちらの schema を真値として使う。

---

## 12. テンプレートバージョニング

- TemplateProfile は immutable、更新時は新 `version` を発行
- Project は `template_profile_id@version` を固定参照
- 古い Project を開く時：固定バージョンで再レンダ可能
- 最新へ切替は明示 UI（差分確認付き）

---

## 13. 将来拡張

| 項目 | Phase |
|---|---|
| pptx 以外の出力（Google Slides, Keynote） | 3 |
| DOCX / PDF 直接生成 | 3 |
| サンドボックス化したカスタムプラグイン | 3 |
| 図表タイプの AI 自動生成（ユーザー指示から新プラグイン提案） | 4 |
| テンプレート間の自動マイグレーション（A → B テンプレに乗せ替え） | 2 |
