# 07. Phase 2 設計書 — プロダクション品質化

**文書名**：SlideForge Phase 2 — Slot アーキテクチャ / Figure 拡張 / 画像 / テーマ継承 / Visual QA
**版**：Draft v0.1
**参照**：`SlideForge_概要設計書.md` §3.3, `04_template_and_plugin.md`, `01_prompt_engineering.md`

---

## 1. 目的とスコープ

Phase 1 では、FastAPI + AWS Lambda + `python-pptx` を軸に「入力テキスト → Blueprint → PPTX」のエンドツーエンド経路を確立した。7 種の figure renderer、LLM による Blueprint 生成、テンプレート登録・再利用、プレースホルダ漏れ防止といった基礎は一通り動作しており、本 Phase 2 ではこれらを **プロダクション品質へ引き上げる** ことを目的とする。

Phase 2 のゴールは次の 3 点に集約される。

1. **テンプレートに忠実な描画** — 顧客が持ち込んだ `.pptx` テンプレートの配色・フォント・ページごとのレイアウト（タイトル位置・本文領域・余白）を実際の出力に反映する。現状ハードコードされている `DEFAULT_PALETTE` / `DEFAULT_FONT` / `DEFAULT_BODY_AREA` を、テンプレートから抽出した `design_tokens` と「スロット（描画枠）」に置き換える。
2. **表現力の拡張** — 現在 7 種に限定されている figure を、matrix / pyramid / org_chart / gantt / swot / kpi / quote などのビジネス頻出図と、画像スロット（写真・スクショ・ロゴ）まで拡げる。Blueprint スキーマと LLM プロンプトを並行して更新する。
3. **壊れないレンダ（Visual QA）** — overflow / placeholder 漏れ / 配色崩れを CI で自動検出する仕組み（golden-file テスト・静的チェッカ・レンダ後スナップショット差分）を導入し、リグレッションをブロックする。

一方、**スコープ外** は次のとおり明示する。

- 生成 LLM の差し替え・セルフホスト化（Claude 固定を維持）
- マルチテナント基盤（認証・課金・組織管理）の本格実装
- 海外展開（多言語 UI、リージョン分散、i18n プロンプト）
- 音声・動画・アニメーションの生成
- 複数ユーザによる同時編集・共同コメント

参照: `docs/SlideForge_概要設計書.md` §3.3「Phase 2 で扱う範囲」、`docs/04_template_and_plugin.md` §2「テンプレート契約」、`docs/01_prompt_engineering.md`「Blueprint スキーマと figure カタログ」。

---

## 2. Phase 1 現状評価

Phase 1 の実装は「動くが、テンプレートに追従せず、表現が限定的で、壊れを検出できない」状態にある。以下 5 軸で現状を整理する。

| 観点 | 実装状況 | 具体的制約 | 根拠 (file:line) |
| --- | --- | --- | --- |
| body_area 固定 | `DEFAULT_BODY_AREA` を全スライドに一律適用 | テンプレートのどのページを割り当てても本文領域が 12.3"×5.4" に固定され、表紙・章扉・本文で枠が同じ | `app/render/layout_renderer.py:17` |
| palette 固定 | `DEFAULT_PALETTE`（紫系 `#8B7AB8` ほか）をハードコード | テンプレの配色を無視し、常に同一の紫系カラーパレットで描画される | `app/render/shapes.py:28-42` |
| フォント固定 | `DEFAULT_FONT = "Noto Sans JP"` をハードコード | テンプレ側のテーマフォント（例: Meiryo / Yu Gothic）が無視される | `app/render/shapes.py:45` |
| figure 7 種のみ | `registry.py` 登録済みの 7 種のみ描画可能 | matrix / pyramid / org_chart / gantt / swot / kpi / quote / image 系が出せず、「表現できない → 無理に bullet_list に退避」が発生 | `app/render/figure_renderers/registry.py`、`app/api/prompts/blueprint_system.txt:14-17` |
| 画像スロット無し | Blueprint スキーマに image 概念が無い | 写真・スクショ・ロゴを指定する経路が存在せず、ブランドビジュアルがテキストのみになる | `app/api/models/schemas.py:16-24`（`FigureType` Literal） |
| design_tokens 空 | `TemplateProfile.design_tokens` は定義されているが常に `{}` | テーマ抽出パスが未実装で、テンプレート取り込み時点から色・フォント情報が失われている | `app/api/models/schemas.py:32`、`app/api/services/template_registry.py`（ルールベース分類のみ） |
| template_slide_index 自動循環 | Blueprint の slide を template page に単純循環割当 | テンプレの「表紙 / 目次 / 本文 / 章扉 / about / disclaimer」の意味論が `content` 以外ほぼ活きない | `app/api/models/schemas.py:67`、`app/api/services/template_registry.py` |
| Visual QA 無し | overflow 検出・golden-file テスト・崩れ検出が存在しない | プレースホルダ漏れ以外のリグレッション（text overflow、figure はみ出し、色ズレ）が CI を通ってしまう | tests 配下に golden なし、`tests/unit/test_layout_renderer.py:118-132` のみが placeholder leak を守る |
| EMU / placeholder 最低ライン | `inch()` / `_i()` による EMU int 化、レンダ時文字列 strip | 「落ちない」最低ラインは守られているが「正しい」ではない | `app/render/shapes.py:17-24`、`tests/unit/test_layout_renderer.py:118-132` |

補足を軸ごとに 1 行で添える。

- **body_area 固定**: `layout_renderer.py:17` の `DEFAULT_BODY_AREA = EMUBox(inch(0.5), inch(1.6), inch(12.3), inch(5.4))` がすべての `template_slide_index` に無関係に使われるため、章扉の大きなタイトル領域や表紙のセンタリング領域をテンプレ側で持っていても反映されない。
- **palette 固定**: `shapes.py:28-42` で定義される `DEFAULT_PALETTE`（primary: `#8B7AB8` 等）が figure renderer 全体から直接参照され、テンプレ由来の色を渡す口が設計に存在しない。
- **フォント固定**: `shapes.py:45` の `DEFAULT_FONT = "Noto Sans JP"` も同様で、テーマフォント継承のパスが通っていない。
- **figure 7 種のみ**: `registry.py` の登録は `table / cards_grid / two_column / timeline / stat_callout / bullet_list / comparison` の 7 種。`blueprint_system.txt:14-17` の enum と `schemas.py:16-24` の `FigureType` Literal がこの 7 種を三重に固定している（追加には 3 箇所同時変更が必要）。
- **画像スロット無し**: Blueprint / Figure のどちらにも `image_slot` や `asset_ref` に相当するフィールドが無く、renderer 側にも画像配置 API が無い。
- **design_tokens 空**: `schemas.py:32` に `design_tokens: dict[str, Any] = {}` が宣言されているが、`template_registry.py` はレイアウト分類（cover / toc / section_divider / content / about / disclaimer）のルールベース判定のみで、XML からの色・フォント抽出は行っていない。
- **Visual QA 無し**: `tests/unit/test_layout_renderer.py:118-132` は `{{placeholder}}` 文字列の残存のみを検証しており、レンダ後 PPTX の shape 座標・overflow・色一致を担保するテストは存在しない。

これらの制約は Phase 1 における **意図された技術的負債** であり（`docs/SlideForge_概要設計書.md` §3.1 で「Phase 1 は最短で E2E を通すことを優先し、テーマ継承・Figure 拡張・Visual QA は Phase 2 に繰り延べる」と明記）、Phase 2 で §3 以降に示す Slot アーキテクチャ / Figure 拡張 / 画像スロット / テーマ継承 / Visual QA の 5 施策により段階的に解消する。

---

## 3. 類似サービスリサーチと示唆

Phase 1 の pptmaker は、図表 7 種（`table` / `cards_grid` / `two_column` / `timeline` / `stat_callout` / `bullet_list` / `comparison`）に閉じ、配色・フォントはテンプレートを無視して固定値をハードコード（`app/render/shapes.py:28-45`）、`body_area` は全スライド共通箱（`app/render/layout_renderer.py:17`）、画像スロット無し、という制約を抱えている。結果として「コンサル提案書っぽい密度」が出せていない。本節では、Phase 2 の設計方針を定める前段として、類似 AI プレゼンサービスと、社内コンサルが日常的に書く McKinsey / BCG / Bain 的スタイルを参照し、**取り込む要素／取り込まない要素**を明示する。

### 3.1 類似サービス比較表

主要な AI プレゼン生成サービス 6 種を、骨格生成・テンプレ忠実度・図表表現力・反復編集・想定ユース・本プロダクトへの示唆の観点で整理する。数値的ベンチマークは避け、広く知られている定性的特徴に限って記述する。

| サービス | 骨格生成 | テンプレ忠実度 | 図表表現力 | 反復編集 | 想定ユース | 本プロダクトへの示唆 |
|---|---|---|---|---|---|---|
| Gamma | LLM first-draft が中心。短いプロンプトからアウトライン → カード型スライドを一括生成 | 低〜中。Web/カード型がネイティブで、pptx 書き出しは副次的 | カード密度は低め。図表は簡易。アイコン・画像の自動配置が強い | カード単位の regenerate、部分書き換えが UI 化 | 個人の軽いピッチ、ブログ的資料 | 骨格を LLM で一発生成する UX は参考になるが、pptx 前提の密度は取り込まない |
| Beautiful.AI | スライド内要素を追加すると制約ベースで自動再配置（スマートスライド） | 中。テンプレ＝スロット制約で整合性を保つ | 図表プリミティブは限定的だが、追加時に破綻しない | 要素追加 → 自動レイアウト、スタイルは全体整合 | 営業資料、社内共有 | **slot ベースの smart layout** は Phase 2 の核として取り込む（§4） |
| Tome | ストーリーテリング志向、ナラティブ単位の生成 | 低。Web ネイティブで pptx 非前提 | 画像・動画・埋め込みに強く、定量図表は弱い | ページ単位の再生成 | 事業ピッチ、コンセプト紹介 | Web ネイティブ表現は取り込まない（出力は .pptx 固定） |
| Canva (AI Presentations) | プロンプト → 既存テンプレへのコンテンツ流し込み | 高（ただし Canva 自社テンプレ群に対して） | 図表は弱め。装飾・画像レイアウトは強い | テンプレ切替・要素差替え | マーケ・学校・個人ブランディング | ブランドキット（色・フォント継承）の概念は取り込む。巨大テンプレライブラリは不要 |
| Pitch | チーム同時編集・コラボ前提。テンプレはデザイナ系で整っている | 中〜高 | 図表はビジネス標準レベル。チャート・表は実務水準 | 共同編集、コメント、バージョン | SaaS / スタートアップの社外提案 | テンプレの「きちんと感」は参考。同時編集は本プロダクト対象外 |
| Decktopus | フォーム駆動（目的・聴衆・トーンを入力）→ スライド生成 | 中。テンプレは固定的 | 図表は定型。ビジネスカジュアル寄り | フォーム再入力 → 再生成 | 提案・トレーニング・ウェビナー | 「構造化入力 → 生成」の UX は `02_ui_ux_design.md` 側と接続し得る |

上表から読み取れる共通傾向は、(a) LLM による骨格一発生成はコモディティ化している、(b) **差別化は「テンプレ忠実度 × 図表表現力」の軸にシフトしている**、(c) Web ネイティブ勢（Gamma / Tome）と pptx 前提勢（Beautiful.AI / Pitch）で設計思想が分岐している、の 3 点である。本プロダクトは社内コンサルの .pptx 納品が最終成果物であるため、後者の系譜に属する。

### 3.2 コンサルスタイル（McKinsey / BCG / Bain 的スタイル）の特徴

戦略コンサル系ファームで標準化された提案書スタイルは、長年にわたり「情報密度を高く保ったまま、読み手の認知負荷を最小化する」方向に収束している。主要な規範を以下に整理する。

- **1 スライド 1 メッセージ（headline message）**: スライド上部に結論文（完結した叙述文、通常 1〜2 行）を置き、本文はそれを支える根拠として構成する。タイトルが体言止めや「〜について」になるのは避ける。
- **Situation / Complication / Resolution の情報構造**: バーバラ・ミントのピラミッド原則に由来する SCR 構造。提案書全体のみならず、セクション単位・スライド単位でも再帰的に適用される。
- **データ密度の高さ**: 1 スライドに表・数値・脚注（出典）が同居する。空白を恐れず、しかし意味のない装飾は置かない。数値には必ず単位と出典が付随する。
- **grid の規律**: 縦横の基準線（通常 12 カラム相当）に沿って要素を揃える。余白・行間・フォントサイズのスケールは資料全体で一貫する。body_area を「1 つの固定箱」ではなく、**複数スロットの集合**として扱う設計が前提となる。
- **figure の定番セット**: 以下は戦略コンサルで常用される図表であり、本プロダクトでも最低限カバーすべき基礎語彙となる。

| figure | 用途 |
|---|---|
| 2x2 matrix | セグメンテーション、優先度付け（BCG PPM 等） |
| pyramid | 階層構造、ロジックツリー、ミント式ピラミッド |
| waterfall | 要因分解（売上・利益ブリッジ等） |
| swot | 内外環境分析 |
| org_chart | 組織・ガバナンス構造 |
| gantt | プロジェクト計画・マイルストーン |
| process_flow | ステップ・フェーズ遷移 |
| stack_bar | 構成比の時系列比較 |
| pull_quote | インタビュー引用、示唆の強調 |

- **visual の抑制**: 色数は 2〜3 色にブランドカラーを加えた構成が基本で、アクセント色は 1 色に限定する。グラデーション・影・3D は原則使わない。フォントも 1 ファミリ 2 ウェイトに収める。

pptmaker は社内コンサル用途を主ターゲットとするため、Gamma / Tome 系の「軽い・カード的・Web ネイティブ」な表現ではなく、**コンサルスタイル側（高密度・grid 規律・定番 figure 網羅・visual 抑制）を基軸に置くべき**である。Phase 2 の設計は、この方針を前提に、Beautiful.AI 由来の slot / smart layout 概念を実装基盤として採用する形で進める。

### 3.3 取り込む示唆 / 取り込まない判断

**取り込む**

- Beautiful.AI 流の **smart layout**（slot ベース、要素追加時に自動再配置） → §4 で Slot モデル化し、`body_area` の固定箱（`app/render/layout_renderer.py:17`）を置き換える。
- **コンサル定番 figure の網羅**（matrix / pyramid / swot / gantt / org_chart / kpi / quote / icon_list / process_flow / waterfall / stack_bar 等） → §5 で現行 7 種から 20+ 種へ拡張し、`app/render/shapes.py` の固定色参照（:28-45）も figure 側で解消する。
- **1 スライド 1 メッセージの headline 構造** → 既存 LLM prompt を強化し、スライド JSON に `headline_message` フィールドを必須化。`docs/01_prompt_engineering.md` 側の指示テンプレと連携する。
- **ブランドキット（テンプレ由来の色・フォント継承）** → §7 のテーマ継承で、テンプレ .pptx のマスタ/スライドレイアウトから theme color と font を抽出し、`shapes.py` のハードコード固定値を駆逐する。

**取り込まない**

- Canva 系の **巨大テンプレライブラリ**: 本プロダクトは顧客（社内コンサル）が自前テンプレを持ち込む前提のため、自社テンプレを大量保有する必然性がない。
- Tome の **Web ネイティブ表現**: 出力は .pptx 固定（`docs/SlideForge_概要設計書.md` の前提）であり、Web アニメーション・埋め込み動画等は対象外。
- Pitch の **同時編集 / コラボ機能**: `docs/SlideForge_概要設計書.md` §1.3 においてチームコラボは対象外と定義済み。1 ユーザー 1 セッションの非同期生成モデルを維持する。

---
## 4. Slot ベースアーキテクチャ転換

Phase 1 実装では、すべての content スライドに対して固定の `DEFAULT_BODY_AREA`
（`app/render/layout_renderer.py:17`）を描画領域として用いていた。この固定矩形は
テンプレートの実際のプレースホルダ座標・余白・ロゴ位置・タイトル帯を一切参照しない
ため、figure が既存レイアウト要素を覆い潰す事故、あるいは逆にテンプレ側の広い領域を
活かせない事故が多発している。また `TemplateProfile.design_tokens` / `layouts`
（`app/api/models/schemas.py:27-35`）は dict 型で宣言されているのみで中身が空であり、
`docs/04_template_and_plugin.md` §5 に記載済みの placeholder slot 抽出仕様が実装に
反映されていない。

本章では、テンプレート各ページから placeholder を抽出して「slot（箱）」として明示
保持し、Blueprint／Renderer／sanitizer をその slot に紐づけて動作させる
アーキテクチャへの転換方針を定義する。

### 4.1 Slot の定義（概念）

Slot とは「テンプレートページ内で、Blueprint content が流し込まれる矩形領域」を
指す。`SlideSpec.template_slide_index`（`app/api/models/schemas.py:67`）は
「どのテンプレページを下敷きにするか」を既に保持しているが、slot はその**ページ内
にある箱**を表現する粒度の概念である。

```
 TemplateProfile (v1.1)
 ├─ layouts[]
 │   └─ layout "content"
 │        ├─ source_slide_index: 4          ← ppt/slides/slide5.xml
 │        ├─ slots[]                        ← 本章で新設
 │        │    ├─ slot "title"       (text,   role=title)
 │        │    ├─ slot "body_main"   (figure, 主要コンテンツ箱)
 │        │    └─ slot "footnote"    (text,   role=note)
 │        └─ fixed_elements[]              ← ロゴ・装飾（不可触）
 │
 ↓ 参照
 SlideSpec (Blueprint)
   content.slots = {
     "title":     { text: "..." },
     "body_main": { figure: "table", data: {...} },
     "footnote":  { text: "..." },
   }
 ↓ 描画
 LayoutRenderer
   for slot in layout.slots:
     payload = content.slots[slot.id]
     renderer_for(slot.kind).render(payload, slot.rect)
```

テンプレ─slot─blueprint─renderer の 4 層を分離することで、figure_type と座標を
直交化し、テンプレ差し替え時にも Blueprint 側の変更を不要にする。

### 4.2 TemplateProfile へのスキーマ追加

`docs/04_template_and_plugin.md` §2 の TemplateProfile v1.0 を継承し、各 layout に
`slots` 配列を必須化する。本節以降、本スキーマを **TemplateProfile v1.1** と呼称
する。

```yaml
# TemplateProfile v1.1
version: "1.1"
name: "corp_default"
design_tokens:
  font_family_jp: "Noto Sans JP"
  color_primary:  "#0B3D91"
layouts:
  - id: "content"
    source_slide_index: 4          # 0-origin, ppt/slides/slide5.xml
    slots:
      - id: "title"                # role=title, placeholder 由来
        kind: "text"
        rect: { x: 914400, y: 457200, cx: 10287000, cy: 685800 }
        role: "title"
      - id: "body_main"            # 主要コンテンツ箱
        kind: "figure"             # figure_type を置ける箱
        rect: { x: 457200, y: 1524000, cx: 11277600, cy: 4953000 }
      - id: "footnote"
        kind: "text"
        rect: { x: 457200, y: 6629400, cx: 11277600, cy: 228600 }
        role: "note"
    fixed_elements:                # ロゴ・装飾（renderer は触らない）
      - { kind: "pic",  rect: { x: 11887200, y: 228600, cx: 914400, cy: 457200 } }
      - { kind: "line", rect: { x: 457200,   y: 1371600, cx: 11277600, cy: 0 } }
```

`kind` の列挙と意味論を以下に示す。

| kind     | 説明                                         | 想定 payload 例                       |
|----------|----------------------------------------------|---------------------------------------|
| `text`   | 段落テキスト（タイトル・注記等）             | `{ "text": "..." }`                   |
| `figure` | figure_type レンダラに委譲する箱             | `{ "figure": "table", "data": {...}}` |
| `image`  | 画像プレースホルダ                           | `{ "image_ref": "assets/a.png" }`     |
| `list`   | 箇条書き専用箱（text より強い整形制約）      | `{ "items": ["...", "..."] }`         |
| `table`  | 表レンダラ専用箱（figure の特殊化）          | `{ "headers": [...], "rows": [...] }` |
| `fixed`  | 触らない（抽出結果に載るが Blueprint 不参照）| —                                     |

`rect` は **EMU（English Metric Unit, 914400 EMU = 1 inch）** を正規形とし、
`inch()` 等のヘルパで生成する既存慣習と整合させる。

### 4.3 Slot 抽出アルゴリズム

テンプレ `.pptx` を展開し、`ppt/slides/slide{N+1}.xml`（`N` は 0-origin の
`source_slide_index`）を走査する。走査は以下の規則で行う。

1. `<p:sp>` のうち `<p:nvSpPr>/<p:nvPr>/<p:ph>` を持つものを **slot 候補** とする。
2. `<p:ph>` の `type` 属性から role を推定する。以下の対応表に従う。
3. `<p:ph>` の `idx` 属性（同一ページ内の placeholder 連番）を保持し、`type` が
   重複する場合の安定 ID に用いる。
4. 子要素 `<p:spPr>/<a:xfrm>/<a:off>` と `<a:ext>` から EMU 座標 `(x, y, cx, cy)`
   を取得し `rect` を構築する。`<a:xfrm>` が存在しない placeholder は
   **layout / master 側から継承**し、最終的に解決できない場合は当該 slot を破棄
   して警告ログを出力する。
5. `<p:ph>` を持たない `<p:sp>` / `<p:pic>` / `<p:cxnSp>` は `fixed_elements`
   として抽出し、Blueprint からは参照不能とする。

| `<p:ph type="...">` | 推定 role   | 既定 slot id    | 既定 kind |
|---------------------|-------------|-----------------|-----------|
| `title` / `ctrTitle`| `title`     | `title`         | `text`    |
| `subTitle`          | `subtitle`  | `subtitle`      | `text`    |
| `body`              | `body`      | `body_main`     | `figure`  |
| `ftr`               | `note`      | `footnote`      | `text`    |
| `dt`                | `date`      | `date`          | `text`    |
| `sldNum`            | `page_num`  | `page_num`      | `text`    |
| （type 未指定 / `obj`）| `object`  | `body_{idx}`    | `figure`  |

Python 側では抽出結果を以下のデータクラスで保持する。

```python
# app/template/slot.py
from dataclasses import dataclass
from typing import Literal, Optional

SlotKind = Literal["text", "figure", "image", "list", "table", "fixed"]

@dataclass(frozen=True)
class EMURect:
    x: int; y: int; cx: int; cy: int

@dataclass(frozen=True)
class Slot:
    id: str                       # layout 内で一意
    kind: SlotKind
    rect: EMURect
    role: Optional[str] = None    # "title" | "body" | "note" | ...
    idx: Optional[int] = None     # <p:ph idx="..."> を保持
```

抽出処理は `app/template/slot_extractor.py`（新設）に集約し、
`TemplateProfile.load()` の内部で呼び出す。抽出結果は TemplateProfile v1.1 の
YAML と**等価**になるよう設計し、CLI で YAML へシリアライズ可能にする。

### 4.4 Blueprint からの Slot 参照

`SlideSpec.content` に slot id をキーとする辞書構造 `slots` を新設する。互換性の
ため、`slots` 未指定時は既定スロット（§4.3 の対応表）に fallback する。

```yaml
# Blueprint 例
SlideSpec:
  index: 5
  layout: "content"
  template_slide_index: 4
  figure_type: "table"
  headline_message: "準委任契約により、5月1日以降は開発工数ベースで継続支援する。"
  content:
    slots:
      title:     { "text":   "ご依頼事項と契約形態" }
      body_main: { "figure": "table",
                   "data":   { "headers": ["項目","内容"],
                               "rows":    [["契約形態","準委任"],
                                           ["開始日","2026-05-01"]] } }
      footnote:  { "text":   "※ 2026年4月時点" }
```

**`headline_message` は §3.2 のコンサルスタイル規範「1 スライド 1 メッセージ」を実装に反映するために新設する必須フィールド**である。従来 `title` に押し込まれがちだった「結論文」を title から分離し、完結した叙述文（主語＋述語、1〜2 行、体言止め禁止）として扱う。レンダ側は slot `headline` が定義されているテンプレではそこに、無ければ title 直上に 1 帯を描画する（描画仕様は §4.3 の fallback 経路に準ずる）。LLM 出力スキーマとバリデーション規則は §5.5 で規定し、`tests/integration/test_headline_required.py` で三層（入力・DB・描画）の必須性を担保する。

LLM からの出力は従来のフラットな `content`（`title`/`bullets`/`table` 等が
トップレベルに並ぶ形）も許容する。フラット形式を v1.1 の slot 形式に変換する
責務を **sanitize 層** に集約し、既存 `app/api/services/blueprint_builder.py` の
sanitizer を拡張する形で実装する。変換規則は以下のとおり。

| フラット key      | 割当先 slot id                        | 補足                             |
|-------------------|---------------------------------------|----------------------------------|
| `title`           | `title`                               | role=title の slot に投入        |
| `subtitle`        | `subtitle` → 無ければ `title` 次行    |                                  |
| `bullets`         | kind=`list` → 無ければ kind=`figure`  | `figure_type=bullets` として解決 |
| `table` / `chart` | kind=`figure` かつ id=`body_main`     | `figure_type` は SlideSpec を優先|
| `note` / `footer` | `footnote`                            |                                  |

### 4.5 LayoutRenderer の改修

`app/render/layout_renderer.py:17` の `DEFAULT_BODY_AREA` は、slot 抽出に失敗した
ときの **緊急フォールバック** にデグレードする。通常経路は layout.slots を
反復して描画する。

```python
# layout_renderer.py (After)
def render_content_slide(slide_xml: str, req: RenderRequest,
                         profile: TemplateProfile, ctx: RenderContext) -> str:
    layout = profile.layout_for(req.template_slide_index)   # NEW
    slots  = layout.slots                                   # NEW
    content_slots = (req.content or {}).get("slots", {})

    if not slots:
        logger.warning("slots missing for layout=%s; falling back to DEFAULT_BODY_AREA",
                       layout.id)
        return _render_with_default_body_area(slide_xml, req, ctx)

    for slot in slots:
        payload = content_slots.get(slot.id)
        if payload is None:
            continue  # 空 slot はテンプレ既定のまま残す
        if slot.kind == "figure":
            renderer = renderer_for(payload["figure"])
            shapes   = renderer.render(payload["data"], slot.rect, ctx)
        elif slot.kind in ("text", "list"):
            shapes   = render_text_slot(payload, slot.rect, slot.role, ctx)
        elif slot.kind == "image":
            shapes   = render_image_slot(payload["image_ref"], slot.rect, ctx)
        elif slot.kind == "table":
            shapes   = render_table_slot(payload, slot.rect, ctx)
        else:
            continue
        slide_xml = splice_shapes(slide_xml, shapes)
    return slide_xml
```

`DEFAULT_BODY_AREA` への fallback は WARN ログを必ず発生させ、Phase 2 最終段では
error に昇格させる（§4.6 ステップ 4）。

### 4.6 段階移行

以下の 4 ステップで段階的に切替える。各ステップ間で `make test` / E2E が green を
維持することを要件とする。

| ステップ | 内容                                                      | fallback 扱い |
|----------|-----------------------------------------------------------|---------------|
| 1        | slot 抽出器のみ実装、TemplateProfile に `slots` 格納      | 未使用（ログ出力のみ）|
| 2        | LayoutRenderer を slot-aware に切替、fallback 経路は維持  | WARN          |
| 3        | Blueprint sanitizer 拡張、LLM プロンプトに slot id を注入 | WARN          |
| 4        | 既定スロット fallback を warning → error に昇格          | ERROR（fail fast）|

ステップ 1 完了時点ではランタイム挙動は一切変わらず、TemplateProfile の中身が
埋まるのみである。ステップ 2 で初めて描画経路が slot を参照し始めるが、抽出失敗
時は従来挙動にフォールバックするため、テンプレ未整備でも回帰が発生しない。
ステップ 3 で LLM 出力が直接 slot id を指す形に寄せられ、ステップ 4 で fallback
が禁止されることで、全テンプレページが TemplateProfile v1.1 の契約に準拠する。

---

## 5. Figure カタログ拡張（7 → 20+）

Phase 1 では 7 種の figure_type（`table`, `cards_grid`, `two_column`, `timeline`, `stat_callout`, `bullet_list`, `comparison`）を実装し、`app/render/figure_renderers/` 配下に 1 ファイル 1 レンダラの形で登録する構成を確立した。Phase 2 ではこれを 20 種以上に拡張し、提案書・報告書・企画書など業務で頻用される構図を網羅する。同時に、現状 `blueprint_system.txt` と `schemas.py` の二重管理になっている figure_type 列挙を単一真値（`list_capabilities()`）から動的注入する仕組みへ移行する。

### 5.1 追加する figure_type 一覧

以下 13 種を追加し、既存 7 種と合わせて計 20 種とする。既存 1–7（table, cards_grid, two_column, timeline, stat_callout, bullet_list, comparison）は省略。

| #  | figure_type    | 目的                         | 想定入力                                                     | 代表利用ページ        | 優先度 |
|----|----------------|------------------------------|--------------------------------------------------------------|-----------------------|--------|
| 8  | matrix_2x2     | 2 軸 4 象限分類              | `axes{x,y}`, `quadrants[4]`                                  | 戦略位置付け          | P0     |
| 9  | pyramid        | 階層ピラミッド               | `levels[3-5]`                                                | 優先度・KPI tree      | P0     |
| 10 | org_chart      | 組織図・階層                 | `nodes`, `edges`                                             | 体制図                | P0     |
| 11 | gantt          | ガント / ロードマップ        | `tasks`, `milestones`                                        | スケジュール          | P0     |
| 12 | swot           | SWOT 4 象限                  | `strengths/weaknesses/opportunities/threats`                 | 現状分析              | P0     |
| 13 | kpi_dashboard  | 数値カードグリッド           | `metrics[{value,label,delta}]`                               | 月次報告              | P1     |
| 14 | pull_quote     | 引用強調                     | `quote`, `attribution`                                       | 導入・締め            | P1     |
| 15 | image_slot     | 画像配置（§6 連携）          | `image_ref`, `caption`                                       | 写真・スクショ        | P0     |
| 16 | icon_list      | アイコン付箇条書き           | `items[{icon,title,body}]`                                   | サービス紹介          | P1     |
| 17 | process_flow   | 水平プロセス                 | `steps`, `arrows`                                            | フロー説明            | P0     |
| 18 | stack_bar      | 積み上げ棒                   | `series`, `categories`                                       | 構成比推移            | P1     |
| 19 | waterfall      | ウォーターフォール           | `start`, `changes[]`, `end`                                  | 収益変動              | P2     |
| 20 | cost_breakdown | 費用内訳                     | `total`, `items[{label,amount}]`                             | 見積                  | P1     |

**優先度の根拠:** P0 は McKinsey/BCG 系の提案書で使用頻度が高く、かつ社内既存成果物でも反復的に現れる図版から選定している（matrix_2x2・swot・process_flow・gantt・pyramid・org_chart・image_slot）。P1 は二次的だが社内利用事例のある表現（kpi_dashboard・icon_list・stack_bar・cost_breakdown・pull_quote）、P2（waterfall）は描画ロジックが複雑で配色・数値スケールなどテーマ依存が大きいため、Phase 2 後半に回す。

### 5.2 新規 figure_type の input schema（抜粋 3 種）

代表として P0 の 3 種を YAML で書き下す。全 13 種の完全な schema は `app/render/figure_renderers/extended/*.py` の `input_schema` クラス変数に実体がある。

**matrix_2x2**

```yaml
figure_type: matrix_2x2
axes:
  x:
    label: string        # e.g. "市場成長率"
    low: string          # 左端ラベル
    high: string         # 右端ラベル
  y:
    label: string
    low: string
    high: string
quadrants:               # 必ず 4 要素。順序 = [TR, TL, BL, BR]
  - title: string
    body: string
    items: [string]      # 省略可、最大 5
  # ... 合計 4
```
> `validate()` の役割: `quadrants` が厳密に 4 要素であること、`axes.{x,y}.label` が非空であること、`items` の件数上限 5 の確認。

**swot**

```yaml
figure_type: swot
strengths:
  items: [string]        # 1..6
weaknesses:
  items: [string]
opportunities:
  items: [string]
threats:
  items: [string]
```
> `validate()` の役割: 4 セクションすべてが存在し、各 `items` が 1 件以上・6 件以下。空セクションは LLM 側の thin output を検知する目的で明示エラーとする。

**gantt**

```yaml
figure_type: gantt
total_weeks: int         # 1..26
tasks:
  - label: string
    start_week: int      # 0..total_weeks-1
    end_week: int        # start_week < end_week <= total_weeks
    group: string?       # 省略可。同一 group は同色で描画
milestones:
  - label: string
    week: int            # 0..total_weeks
```
> `validate()` の役割: `start_week < end_week`、範囲が `total_weeks` 内、`tasks` は 1..12 件、`milestones` は 0..8 件。範囲外は `FigureValidationError` で拒否する。

### 5.3 動的カタログ注入 — ハードコード廃止

**Before（Phase 1 の現状）**

- `app/api/prompts/blueprint_system.txt` に figure_type 列挙と skeleton 例をベタ書き。
- `app/render/figure_renderers/schemas.py:16-24` の `FigureType = Literal[...]` と手動同期。
- 新規 figure_type を足すと **最低 3 ファイル**（renderer 実装・Literal・プロンプト）を同期する必要があり、Phase 2 で 13 種追加するには破綻する。

**After（Phase 2 の方針）**

- `app/render/figure_renderers/__init__.py:list_capabilities()` を**単一真値（Single Source of Truth）**とする。
- Pydantic の `FigureType` Literal は起動時に `REGISTRY` から動的合成する。ただし静的型チェック（mypy / IDE 補完）を損なわないため、`typing.Annotated` + `TypedDict` の工夫で注釈を残す（実装例は以下）。
- プロンプトの figure_type 列挙部はテンプレート穴埋め方式の `build_blueprint_system_prompt()` で合成し、Anthropic の prompt cache は **合成後の完全文字列に対して** 取る（テンプレ本体は不変なので cache hit 率は従来同等）。

```python
# app/api/prompts/builder.py
from functools import lru_cache
from pathlib import Path
from app.render.figure_renderers import list_capabilities

_TEMPLATE_PATH = Path(__file__).parent / "blueprint_system.tmpl.txt"

@lru_cache(maxsize=1)
def build_blueprint_system_prompt() -> str:
    caps = list_capabilities()  # [{figure_type, description, input_schema}, ...]
    enum_block = "\n".join(
        f"- `{c['figure_type']}`: {c['description']}" for c in caps
    )
    schema_block = "\n\n".join(
        f"### {c['figure_type']}\n```json\n{c['input_schema_json']}\n```"
        for c in caps
    )
    tmpl = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return tmpl.format(
        figure_type_enum=enum_block,
        figure_type_schemas=schema_block,
        n_types=len(caps),
    )
```

Pydantic 側の動的 Literal 合成は次の通り。起動時に 1 度だけ実行される。

```python
# app/render/figure_renderers/schemas.py
from typing import Literal, cast
from app.render.figure_renderers import list_capabilities

_types = tuple(c["figure_type"] for c in list_capabilities())
FigureType = cast(type, Literal[_types])  # 実体は Literal[...], 静的型は str
```

### 5.4 プラグイン拡張 IF

`docs/04_template_and_plugin.md §7` で提案した Python entry points ベースの拡張機構は、**Phase 2 では "内部プラグイン" のみ**採用する。

- `app/render/figure_renderers/extended/` 配下を `__init__.py` で自動 import（`pkgutil.walk_packages` + `@register` デコレータにより REGISTRY 登録）。
- 既存 7 種は `app/render/figure_renderers/` 直下のまま据え置き（互換維持、pixel diff 0 を担保するため）。
- **テナント独自コードの動的ロード**（外部パッケージの entry point 経由登録）は Phase 3 へ延期する。理由はコード実行のセキュリティ境界・sandboxing が別課題であり、Phase 2 のスコープ（社内単一デプロイ）では不要であるため。

### 5.5 LLM 側の追従

`docs/01_prompt_engineering.md §11` の eval cases を 13 種 × 最低 2 サンプル、合計 26 ケース追加する。

- 配置先: `evals/cases/figure_{figure_type}_{01,02}.yaml`。
- 各ケースは `(input_spec, expected_blueprint, expected_render_pass)` の 3 点組を含む。
- CI では `pytest evals/` がこの YAML を読み、Blueprint 生成 → validate() → render() の三段で回帰を見る。`expected_render_pass = true` のものは実際に PNG を生成して画素誤差 ≤ 1% を確認する。

加えて、§3.2 で導入したコンサルスタイル規範を LLM プロンプトに正式ルールとして組み込む（`docs/01_prompt_engineering.md` §4 のテンプレ更新と連動）。

**プロンプト強化ルール（新規）**

- **`headline_message` 必須化**: §4.4 で新設した `SlideSpec.headline_message` を LLM 出力スキーマに必須フィールドとして反映する。2 段階バリデーション:
  1. 構造検証 — 完結した叙述文（主語＋述語を含み、句点で終わる、1〜2 行、体言止め禁止）。
  2. 内容検証 — `slots.title` のテキストと 70% 以上一致する場合（単なるタイトル再記述）は reject。
- **SCR 構造のヒント注入**: スライドが根拠と結論を伴う場合、`body_main` slot の組み立てを「Situation（前提）→ Complication（論点）→ Resolution（結論）」順で誘導する。SCR を別 slot に機械分解するのではなく、単一スライド内の論理展開として LLM に指示する。
- **密度と抑制のバランス**: 1 スライド内の `figure_type` は 1 種類までとし、`table` と `stat_callout` の併置などを禁止する。コンサルスタイルの「visual 抑制」を強制する。
- **Eval 追加**: 上記 3 ルールの違反例・適合例を `evals/cases/headline_*.yaml` / `evals/cases/scr_*.yaml` / `evals/cases/density_*.yaml` に各最低 3 ケース追加する。

### 5.6 受入条件（本節のみ）

| # | 条件 | 確認方法 |
|---|---|---|
| 1 | 20 figure_type すべてが `renderer_for(name)` でインスタンス化できる | `pytest tests/render/test_registry_completeness.py` |
| 2 | `len(list_capabilities()) == 20` | 同上 |
| 3 | `blueprint_system.txt` に figure_type 列挙がベタ書きで残っていない | `grep -E '^- \`(table\|cards_grid\|...)` が 0 件 |
| 4 | 既存 7 種の出力バイナリが移行前後で pixel diff 0 | `tests/golden/` 配下の baseline PNG と bitwise 比較 |
| 5 | 13 種の eval ケースがすべて pass | `pytest evals/ -k "figure_"` |

---

## 6. 画像スロット設計

本節では、生成 PPTX にユーザー提供の画像を埋め込むための仕組みを定義する。
**画像生成 (text-to-image) はスコープ外**であり、本節はユーザーがアップロードした
静止画アセットをスライド内に配置することだけを対象とする。画像生成 AI との連携は
§6.7 で明示的にスコープ外とした上で、Phase 3 以降の検討事項とする。

### 6.1 ユースケース

Phase 2 で想定するユースケースは次の 3 つに絞る。これ以外の用途
（装飾アイコン、背景パターン等）は当面テンプレート側で吸収する。

1. **会社紹介ページのロゴ / 代表写真**
   提案書冒頭の会社紹介スライドに、提案元企業のロゴおよび代表者写真を配置する。
   ロゴは通常テンプレート固定だが、マルチテナント運用において
   テナントごとにロゴを差し替えるため画像スロット化が必要となる。
2. **実績・事例ページのスクリーンショット**
   過去案件のプロダクト UI スクリーンショットや成果物の写真を 1 枚 / 複数枚配置する。
   縦横比が不揃いのため fit モード (§6.5) の使い分けが最も求められるケースである。
3. **体制図・製品写真**
   プロジェクト体制のメンバー写真や、提案対象プロダクトの製品写真を配置する。
   focal point 指定 (§6.2) により顔や製品中央を意図的に中央配置したいニーズがある。

### 6.2 データモデル

Phase 1 の `Blueprint` / `SlideSpec` / 7 種の `figure_types` には画像参照の概念が
存在しない (`app/api/models/schemas.py`)。Phase 2 では `SlideSpec.content.slots`
の任意 slot が `kind: image` を取り得るよう拡張する。

```yaml
slots:
  hero_photo:
    image_slot:
      asset_id: "ast_01HXYZ..."     # ImageAsset テーブルへの参照
      fit: "cover"                   # cover | contain | fill | fit_width
      focal: { x: 0.5, y: 0.4 }      # 焦点正規化座標（cover 時の切り出し中心）
      caption?: "2026 年 4 月 社内勉強会"
      alt?: "オフィス集合写真"
```

`asset_id` 実体を管理する `ImageAsset` テーブルを新設する。

| カラム | 型 | 備考 |
|---|---|---|
| id | UUID PK | 外部表現は `ast_` プレフィックス付き ULID |
| tenant_id | string | RLS キー、全クエリで強制 |
| project_id | UUID FK | 案件スコープ、テナント共通ロゴ等は NULL |
| s3_key | string | `originals/{tenant}/{project}/{asset}.{ext}` |
| mime | string | `image/png` / `image/jpeg` / `image/webp` |
| bytes | int | サイズ上限 10 MB、超過時 413 |
| width_px / height_px | int | EXIF orientation 正規化後の実寸 |
| checksum_sha256 | string | 重複排除・整合性検証の両用 |
| uploaded_by | UUID | `users.id` への FK |
| created_at | datetime | UTC |

`checksum_sha256` は commit フェーズ (§6.3) で照合し、同一テナント・同一ハッシュの
既存アセットが存在する場合は新規 row を作らず既存 `asset_id` を返す重複排除を行う。

### 6.3 アップロードフロー

テンプレ本体アップロード用の S3 プリサイン発行機構 (`app/api/services/storage.py`)
を再利用し、以下 3 ステップで画像をアップロードする。
Lambda (API) を通してバイナリを中継しない構成とし、API 側の帯域を節約する。

1. **発行**
   `POST /api/projects/{id}/images`
   → `{asset_id, upload_url, fields}` を返す。
   S3 presigned POST (SigV4) を発行し、有効期限は 7 日。
   条件として `Content-Length-Range` (1B–10MB) と `Content-Type` ホワイトリストを埋め込む。
2. **直接転送**
   クライアントは `upload_url` に対して `fields` を multipart POST で送出する。
   Lambda は経由しない。
3. **commit**
   `POST /api/projects/{id}/images/{asset_id}/commit`
   → サーバ側で以下を実施する。
   - S3 オブジェクトの `sha256` を計算し、ステップ 1 で受理した値と照合。
   - Pillow により width / height と EXIF orientation を読み取り、正規化。
   - EXIF メタデータ（特に GPS）を除去して再保存 (§6.6)。
   - `ImageAsset` に row を挿入して 201 を返す。

Content-Type ホワイトリストは **png / jpeg / webp の 3 種のみ** とする。
GIF・SVG・BMP は 400 Bad Request で拒否する。SVG は XXE / スクリプト注入の攻撃面が
広いため、Phase 2 のスコープからは明示的に除外する。

### 6.4 PPTX 埋め込み実装

Phase 1 の `app/render/pptx_assembler.py` は python-pptx の高レベル API
（`slide.shapes.add_picture()` 等）を用いず、ZIP + XML を直接組み立てる方式を採用している。
Phase 2 でも同方式を維持するため、画像埋め込みは以下 4 箇所への追記で実現する。

- `ppt/media/image{N}.{ext}` に画像バイトを ZIP エントリとして追加する。
- `ppt/slides/_rels/slide{N}.xml.rels` に
  `<Relationship Id="rId..." Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image{N}.{ext}"/>`
  を追記する。
- `slide{N}.xml` に `<p:pic>` 要素を追加する。`<p:spPr>` の `<a:xfrm>` に
  EMU 単位の rect（= `slot.rect`）を設定し、fit モードに応じて
  `<a:blipFill>` 配下の `<a:srcRect>` で切り出しを指定する。
- `[Content_Types].xml` に使用拡張子ごとの
  `<Default Extension="png" ContentType="image/png"/>` を冪等に追加する。

埋め込みロジックは以下のシグネチャで実装する。

```python
def embed_image(
    pack: PptxPackage,
    asset: ImageAsset,
    slot: ImageSlotSpec,
) -> ShapeXML:
    ext = MIME_TO_EXT[asset.mime]                         # png / jpeg / webp
    media_idx = pack.next_media_index(ext)
    media_path = f"ppt/media/image{media_idx}.{ext}"
    pack.zip.writestr(media_path, asset.read_bytes())     # S3 から取得済み

    rid = pack.add_relationship(
        slide_idx=slot.slide_idx,
        rel_type=REL_TYPE_IMAGE,
        target=f"../media/image{media_idx}.{ext}",
    )
    pack.content_types.ensure_default(ext, asset.mime)

    src_rect = compute_src_rect(                          # §6.5 参照
        fit=slot.fit,
        focal=slot.focal,
        img_px=(asset.width_px, asset.height_px),
        slot_emu=slot.rect,
    )
    return render_pic_xml(rid=rid, rect=slot.rect, src_rect=src_rect, alt=slot.alt)
```

`ShapeXML` は `slide{N}.xml` の `<p:spTree>` 配下に連結される文字列である。

### 6.5 fit モードと切り出し計算

画像と slot の縦横比が一致しない場合の振る舞いを `fit` 属性で選択する。

| fit | 方針 | EMU rect vs ピクセル rect | 実装 |
|---|---|---|---|
| `cover` | 比率を保ったまま slot を塗りつぶし、画像側を切り出す | 画像側を `srcRect` でトリム、`focal` を中心とする | `<a:srcRect l= t= r= b= />` を生成、EMU rect は slot のまま |
| `contain` | 画像全体を slot 内に収める | 余白で埋める、align は slot 中央 | `<a:xfrm>` の rect を slot 内側に縮小、`srcRect` なし |
| `fill` | 縦横比を無視して引き伸ばす | 警告（非推奨） | `srcRect` なし、rect は slot のまま |
| `fit_width` | 幅を合わせ、高さは画像比で決める | `slot.h` を画像比から再計算、slot 外にはみ出し得る | overflow 検出時 §8 の品質ゲートへ連携 |

デフォルトは `cover`、`focal` の既定値は `(0.5, 0.5)` とする。
`cover` の `srcRect` は OOXML 仕様に従い左/上/右/下の **切り落とし率 × 100000** で表現する。
例として画像比 4:3、slot 比 16:9、`focal = (0.5, 0.4)` の場合、
上下方向にトリミング幅を算出し、焦点を中心に収まるよう `t` / `b` を非対称に計算する。

`fill` は縦横比が大きく乖離すると見栄えが著しく劣化するため、
Blueprint 検証時に警告を出す（§8 品質ゲートへ連携）。
`fit_width` はテキスト段落と並置する用途を想定し、
はみ出しが slot 下限を超える場合は overflow 警告を起票する。

### 6.6 セキュリティ / 上限

- **ウイルススキャン**
  S3 PutObject イベントを契機に Lambda で ClamAV を実行する構成を Phase 2 後半で導入する。
  Phase 2 初期リリースでは MIME 宣言値と magic byte（PNG シグネチャ `89 50 4E 47 ...` 等）の
  突き合わせ検査のみを commit 時に行う。
- **Metadata 除去**
  commit 時に Pillow で EXIF を剥離してから `s3_key` に再保存する。
  位置情報・端末情報の漏洩を防ぐため、orientation 情報のみピクセル回転として
  焼き込み、それ以外の EXIF タグは破棄する。
- **容量上限**
  1 ファイル 10 MB（presigned POST の `Content-Length-Range` で enforce）、
  1 プロジェクト画像総量 200 MB を上限とする。
  200 MB を超える commit は 413 Payload Too Large で拒否する。
  総量は `SUM(bytes) WHERE project_id = ?` を commit トランザクション内で算出する。

### 6.7 スコープ外

以下は Phase 2 のスコープから明示的に除外し、Phase 3 以降の検討事項とする。

- **画像生成 AI 連携**（Stable Diffusion、Claude 画像生成、DALL·E 等）
  プロンプトからの自動生成機能は権利処理・生成品質の両面で独立した設計判断を要するため、
  別フェーズで扱う。
- **画像編集**（トリミング UI、明るさ / コントラスト調整、フィルタ等）
  Phase 2 ではアップロード済み画像を slot 指定 (§6.5) で配置するのみとする。
- **画像検索 / 社内ストック**
  テナント横断の素材ライブラリ、タグ検索、類似画像検索は Phase 3 以降に持ち越す。

---
## 7. テーマ継承 — ppt/theme/theme1.xml

Phase 1 時点では、配色およびフォントは `app/render/shapes.py:28-42` の `DEFAULT_PALETTE`（`Palette(purple="8B7AB8", ...)`）と `app/render/shapes.py:45` の `DEFAULT_FONT = "Noto Sans JP"` にハードコードされており、`TemplateProfile.design_tokens`（`app/api/models/schemas.py:32`）は dict として宣言されているが常に空 dict である。また `app/api/services/template_registry.py` はレイアウト分類のみを行い、`ppt/theme/theme*.xml` には一切アクセスしていない。`FigureRenderer.render()` は `RenderContext(palette, font, ...)` を経由して `palette` を受け取るが、実体は常に `DEFAULT_PALETTE` である。§7 ではこの経路を拡張し、テンプレート固有のテーマを renderer まで伝播させる設計を定義する。

### 7.1 PPTX テーマ構造おさらい

PPTX は ZIP アーカイブであり、テーマ情報は `ppt/theme/` 以下に格納される。構造は以下のとおり。

```
ppt/theme/theme1.xml
  └─ <a:theme>
      ├─ <a:themeElements>
      │    ├─ <a:clrScheme name="...">
      │    │    ├─ <a:dk1>/<a:lt1>/<a:dk2>/<a:lt2>
      │    │    ├─ <a:accent1> .. <a:accent6>
      │    │    └─ <a:hlink>/<a:folHlink>
      │    ├─ <a:fontScheme>
      │    │    ├─ <a:majorFont>
      │    │    │    ├─ <a:latin typeface="..."/>
      │    │    │    ├─ <a:ea typeface="..."/>
      │    │    │    └─ <a:cs typeface="..."/>
      │    │    └─ <a:minorFont> (同構造)
      │    └─ <a:fmtScheme>  … 塗り・線・効果プリセット
```

実テンプレートではマスター毎に `theme2.xml` / `theme3.xml` … が併存することがあるが、**Phase 2 では `theme1.xml` のみを採用**する。複数検出時は警告ログ（`logger.warning("multiple themes detected, using theme1.xml (ignored: %s)", extras)`）を出し、将来の拡張余地として記録のみ残す。

色の表現は下記いずれかの形式で現れるため、両対応が必要である。

```xml
<a:accent1>
  <a:srgbClr val="8B7AB8"/>
</a:accent1>

<a:dk1>
  <a:sysClr val="windowText" lastClr="000000"/>
</a:dk1>
```

`<a:sysClr>` の場合、`lastClr` 属性が PowerPoint が直近に解決した sRGB 値であり、実用上はこれを採用する（未指定時は `windowText=000000`, `window=FFFFFF` の固定マップへフォールバック）。

### 7.2 抽出 API

新規モジュール `app/render/theme_loader.py` を追加する。データクラスは全て `frozen=True` とし、後段のキャッシュ層で hash 可能にする。

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ThemeColors:
    dk1: str; lt1: str; dk2: str; lt2: str
    accent1: str; accent2: str; accent3: str
    accent4: str; accent5: str; accent6: str
    hlink: str; fol_hlink: str

@dataclass(frozen=True)
class ThemeFonts:
    major_latin: str; major_ea: str; major_cs: str
    minor_latin: str; minor_ea: str; minor_cs: str

@dataclass(frozen=True)
class Theme:
    colors: ThemeColors
    fonts: ThemeFonts

def load_theme(pptx_bytes: bytes) -> Theme:
    """ppt/theme/theme1.xml を抽出し Theme を返す。
    失敗時は ThemeLoadError を送出し、呼び出し側で DEFAULT_PALETTE に fallback。
    """
```

XML 解析は `lxml.etree` を用い、名前空間 `a = "http://schemas.openxmlformats.org/drawingml/2006/main"` を固定する。`<a:srgbClr>` と `<a:sysClr>` の両方を辿る小 helper `_resolve_color(elem) -> str` を内部に持つ。

### 7.3 Palette への写像

既存 `Palette`（`shapes.py:28-42`）のスロット名は Phase 1 の実装（`purple_lt` / `amber` / `green` 等、意味論ではなくブランド色名）に強く結びついているため、**スロット名は維持したままテーマから合成**する。これにより renderer 側（`FigureRenderer`, `shapes.*`）は一切変更不要となる。

| Palette slot | 由来（優先順） | フォールバック |
|---|---|---|
| purple (primary) | accent1 | `#8B7AB8` |
| purple_lt | accent1 lighten 40% | `#D9D1E8` |
| purple_dk | accent1 darken 20% | `#6B5C96` |
| purple_bg | accent1 lighten 85% | `#F5F2F9` |
| black (text) | dk1 | `#3A3A42` |
| dark (text sub) | dk2 | `#5E5C6A` |
| muted | dk1 / lt1 中点 | `#9B98A6` |
| border | lt2 | `#E8E6EC` |
| bg_alt | lt1 lighten 2% | `#FAFAFB` |
| amber (accent a) | accent2 | `#C4A05C` |
| green (accent b) | accent3 | `#5E9B7F` |

lighten / darken は HSL 空間で L を線形に調整する。

```python
import colorsys

def _shift_l(hex_rgb: str, delta: float) -> str:
    r, g, b = (int(hex_rgb[i:i+2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = max(0.0, min(1.0, l + delta))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "{:02X}{:02X}{:02X}".format(int(r*255), int(g*255), int(b*255))

def lighten(c: str, pct: float) -> str: return _shift_l(c, +pct)
def darken(c:  str, pct: float) -> str: return _shift_l(c, -pct)
```

合成後に WCAG AA 判定を行う。`contrast(text=black_slot, bg=bg_alt_slot) < 4.5` など主要ペアが閾値を下回った場合は `logger.warning` を発し、`design_tokens.warnings` に記録する（レンダは継続）。

### 7.4 Font への写像

日本語提案書を主用途とするため、`ea`（East Asian）を最優先とする。

| RenderContext slot | 由来（優先順） |
|---|---|
| heading | majorFont.ea → majorFont.latin → `"Noto Sans JP"` |
| body | minorFont.ea → minorFont.latin → `"Noto Sans JP"` |

未インストールフォント検知は、Lambda コンテナイメージ同梱の `/opt/fonts/` 配下 `*.ttf/*.otf` を起動時に列挙し `AVAILABLE_FONTS: frozenset[str]` として保持、突合して未ヒット時は警告 + `"Noto Sans JP"` フォールバックとする。

### 7.5 RenderContext への注入経路

Phase 1 実装（`app/render/layout_renderer.py`）は以下の固定値注入となっている。

```python
# Phase 1
ctx = RenderContext(palette=DEFAULT_PALETTE, font=DEFAULT_FONT, ...)
```

Phase 2 ではテンプレートバイト列からテーマを解決し、`Palette.from_theme` / `font_from_theme` 経由で注入する。

```python
# Phase 2
theme = load_theme(template_bytes)
palette = Palette.from_theme(theme)       # 7.3 のマッピング
font    = font_from_theme(theme)          # 7.4 のマッピング
ctx = RenderContext(palette=palette, font=font, ...)
```

抽出結果は `TemplateProfile.design_tokens` に以下の形で保存する。

```json
{
  "colors": { "purple": "8B7AB8", "purple_lt": "D9D1E8", ... },
  "fonts":  { "heading": "Noto Sans JP", "body": "Noto Sans JP" },
  "theme_source": "theme1.xml",
  "extracted_at": "2026-04-23T00:00:00Z",
  "warnings": []
}
```

解析はテンプレ登録時（`template_registry.register()`）に **1 回だけ** 実行し DB に永続化、以降のレンダ要求はキャッシュから取得する。テンプレ再アップロード時のみ再計算される。

### 7.6 ユーザーオーバライド

テンプレ由来の色をユーザーが拒否・差し替える UI を Phase 2 後半で提供する。

- `TemplateProfile.design_tokens.overrides = {"primary": "#...", "heading_font": "...", ...}` を優先適用
- overrides が存在するスロットは theme 再抽出でも上書きしない（`overrides` は抽出結果とは独立して保存）
- 合成順: `DEFAULT_PALETTE` ← `theme` ← `overrides`（右側優先）

```python
palette = Palette.from_theme(theme).override(profile.design_tokens.get("overrides", {}))
```

### 7.7 段階移行

破壊的変更を避けるため 4 ステップで段階導入する。

| Step | 実装範囲 | feature flag | レンダ挙動 |
|---|---|---|---|
| 1 | `theme_loader` 実装 + unit test（ゴールデン `theme1.xml` 数本） | OFF | 変化なし |
| 2 | `TemplateProfile.design_tokens` 保存開始 | OFF | 依然 `DEFAULT_PALETTE` |
| 3 | feature flag ON、renderer が `design_tokens` 参照 | ON | 既存スナップショットと pixel diff を取得し回帰確認 |
| 4 | `DEFAULT_PALETTE` を **テーマ抽出失敗時の緊急 fallback** に格下げ | 常時 ON | テーマ駆動がデフォルト |

Step 1–2 は既存挙動に影響しないため Phase 2 早期に投入可能である。Step 3 で pixel diff に一定以上の差が出る場合は §7.3 のマッピング表を再調整する（スロット名維持の原則は保つ）。Step 4 到達時点で、ハードコード配色は撤廃ではなく「例外時の最終防衛線」として残す。

---

## 8. Visual QA

Phase 1 では Pydantic スキーマ検証とユニット・統合テスト（`tests/unit/test_layout_renderer.py` ほか、`tests/integration/test_api_smoke.py`, `test_e2e_flow.py`）は整備されているが、以下の QA ギャップが残存している。

- **Golden-file による生成 pptx のバイナリ / PDF / PNG 比較は未整備**
- **Overflow 検出の仕組みが存在せず**、テキストが slot を物理的にはみ出しても検知されない
- プレースホルダ漏れ検査は `tests/unit/test_layout_renderer.py:118-132` で `"本文をここに入れる"` の固定文字列不在を確認するに留まり、テンプレ横断で汎用化されていない

本節では、この 3 点を補う Visual QA の設計を提示する。なお、`app/render/preview.py` が既に LibreOffice を介した pptx → PNG 変換を実装しているため、これを Visual QA レイヤでも再利用する。

### 8.1 QA の 3 層モデル

Phase 2 QA は以下の 3 層に整理する。本節では主に **L2 と L3 を新設**し、L1 は既存の Pydantic / `FigureRenderer.validate()` 機構を踏襲する。

| 層 | 対象 | 手法 | CI 所要 |
| --- | --- | --- | --- |
| L1 Schema QA | Blueprint / SlideSpec / FigureRenderer の入出力 | Pydantic + `FigureRenderer.validate()` | 約 1 秒 |
| L2 Structural QA | pptx XML の静的検査 | lxml で rect, slot 被り, placeholder 未置換 | 約 5 秒 |
| L3 Visual QA | 描画後ピクセル | LibreOffice レンダ + PNG diff | 約 60 秒 |

L1 は入力契約、L2 はレイアウト不変条件、L3 は人間が視認する最終成果物の各レイヤに対応する。段階的に上位層へ上がるほど検査コストが増大するため、CI 常時実行範囲と on-demand 実行範囲を分離する（§8.5 参照）。

### 8.2 L2-1 プレースホルダ未置換検出

既存の部分文字列チェックをテンプレ横断で汎用化する。設計方針:

- テンプレ XML 解析時点で、slide layout / master に定義されている **プレースホルダ既定テキスト**（例: `"クリックしてタイトルを入力"`, `"本文をここに入れる"`, `"サブタイトル"` 等）を抽出し、`TemplateProfile.placeholder_defaults: list[str]` に保存する
- 出力 pptx の各 slide XML に対し、上記リストのいずれかが残存していれば **未置換**として fail させる
- 実装は `app/render/qa/placeholder_guard.py` に新設する

```python
from dataclasses import dataclass
from lxml import etree
from app.templates.profile import TemplateProfile

@dataclass(frozen=True)
class Leak:
    slide_index: int
    placeholder_text: str
    xpath: str

def scan_placeholder_leak(
    profile: TemplateProfile, slide_xmls: list[bytes]
) -> list[Leak]:
    leaks: list[Leak] = []
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    for idx, xml in enumerate(slide_xmls):
        root = etree.fromstring(xml)
        for t in root.iter("{%s}t" % ns["a"]):
            text = (t.text or "").strip()
            if text and text in profile.placeholder_defaults:
                leaks.append(Leak(idx, text, root.getroottree().getpath(t)))
    return leaks
```

本関数は L2 テストから呼び出され、CI 実行時に 1 件でも `Leak` が返れば fail する。`TemplateProfile` の `placeholder_defaults` は Phase 1 の `test_template_loader.py` で検証される `TemplateLoader` に抽出ロジックを追加して生成する。

### 8.3 L2-2 Overflow 検出

Overflow は以下の 3 種類に分類する。

1. **Slot overflow**: shape rect が slot rect を超過する（`x + cx > slot.x + slot.cx` など）。L2 で rect 計算のみで判定可能。
2. **Text overflow**: LibreOffice レンダ後、text frame の内容が frame 高さを超過する。autoshrink off 前提。静的に厳密判定は不可能なので **L3 で最終判定**し、L2 ではヒューリスティクスで `suspicious` 警告のみ出す。
3. **Shape collision**: 非 fixed な shape 同士の rect 重なり。ロゴ・ヘッダ等の `fixed_elements` は除外する。
4. **Grid alignment violation**: §3.2 のコンサルスタイル規範「grid の規律」を静的に強制する。`grid_unit_emu = slide_width_emu / 12` を基準線とし、slot.rect.x / rect.y がこのグリッドから ±0.1 × grid_unit 以上ずれる場合に検出する。Phase 2.5 では **Warn**（テンプレ起因で誤検出が出やすいため）、社内 3 テンプレで誤検出ゼロを確認したのち Phase 3 で Fail に昇格する。

実装は `app/render/qa/overflow.py` に集約する。

```python
from dataclasses import dataclass
from app.render.shapes import ShapeXML, Rect, Slot

@dataclass(frozen=True)
class Violation:
    kind: str   # "slot_overflow" | "shape_collision" | "text_suspicious"
    shape_id: str
    detail: str

def check_slot_bounds(shape: ShapeXML, slot: Slot) -> list[Violation]: ...

def check_shape_collisions(
    shapes: list[ShapeXML], fixed: list[Rect]
) -> list[Violation]: ...

def estimate_text_overflow(
    shape: ShapeXML, text: str, font_size_pt: float
) -> list[Violation]:
    # char count x avg char width (EMU) x line wrap を概算し、
    # frame 高さ超過を "text_suspicious" として警告
    ...
```

#### Text overflow ヒューリスティクス

文字幅は日本語全角 = font size pt × 1.0、半角 = × 0.5 の平均を仮定し、1 行あたり収容文字数を `frame_width_emu / (font_px * avg_char_width_emu)` で近似する。行数 × line height が frame 高さを超える場合に `text_suspicious` を発行する。**確定判定は L3（§8.4）で実レンダリング結果を用いて行う** ため、L2 ではこの警告により PR コメントで注意喚起する程度に留める。

| 違反種別 | 判定層 | Fail / Warn |
| --- | --- | --- |
| Slot overflow | L2 静的 | Fail |
| Shape collision | L2 静的 | Fail |
| Text overflow (static estimate) | L2 ヒューリスティクス | Warn |
| Text overflow (rendered) | L3 ピクセル | Fail |
| Grid alignment | L2 静的 | Warn（Phase 2.5）→ Fail（Phase 3 以降） |

### 8.4 L3 Golden-file diff

#### テスト資産配置

```
tests/visual_qa/
  golden/
    baseline_16_9/slide_01.png ... slide_15.png
    baseline_4_3/slide_01.png ...
    figure_matrix_2x2/slide_01.png
    image_cover/slide_01.png
    long_text/slide_01.png
  fixtures/
    baseline_16_9.blueprint.json
    ...
```

#### 実行フロー

pytest fixture が以下を行う。

1. 対象 blueprint JSON を読み込み、`PptxAssembler` で pptx を生成
2. `app/render/preview.py` の LibreOffice バックエンドで各 slide を PNG 化
3. 既存 golden PNG と **SSIM**（Structural Similarity Index）を計算
4. 閾値判定:

| SSIM | 判定 |
| --- | --- |
| ≥ 0.98 | 合格 |
| 0.95 – 0.98 | 人手レビュー（warn、CI 上は yellow） |
| < 0.95 | Fail |

5. 失敗時は `diff.png`（並列表示 + 差分ヒートマップ）を CI artifact として上げる

#### ケース一覧

| ケース | テンプレ | Blueprint | 検出したい不具合 |
| --- | --- | --- | --- |
| `baseline_16_9` | 16:9 標準 | 15 枚 | 全体レイアウトの大域的崩れ |
| `baseline_4_3` | 4:3 | 同上 | 座標計算の縦横比バグ |
| `figure_matrix_2x2` | 16:9 | 1 枚 | 2x2 象限の文字切れ・バランス |
| `image_cover` | 16:9 | 1 枚 | 画像 fit=cover の切り出し範囲 |
| `long_text` | 16:9 | 1 枚 | text overflow の視覚的検知 |

#### 更新フロー

golden 差分が意図した変更である場合、`pytest --update-golden` で golden PNG を再生成する。変更が大きい場合は、PR に **before / after / diff の 3 面スクリーンショット**を添付し、レビュアが視覚的に承認する運用とする。

```python
# tests/visual_qa/conftest.py 抜粋
@pytest.fixture
def visual_diff(request, tmp_path):
    def _compare(case_name: str, rendered_pngs: list[bytes]):
        golden_dir = Path("tests/visual_qa/golden") / case_name
        for i, png in enumerate(rendered_pngs, 1):
            ssim = compute_ssim(golden_dir / f"slide_{i:02}.png", png)
            if ssim < 0.95:
                write_diff(tmp_path / f"{case_name}_slide_{i:02}_diff.png", ...)
                pytest.fail(f"{case_name} slide {i}: SSIM={ssim:.3f}")
            elif ssim < 0.98:
                request.node.add_report_section("call", "warn",
                    f"SSIM={ssim:.3f} (review required)")
    return _compare
```

### 8.5 CI 組み込み

L1 / L2 と L3 を別ジョブに分離し、実行頻度を調整する。

| ジョブ | 内容 | 実行タイミング | ランタイム |
| --- | --- | --- | --- |
| `pytest.yml`（既存） | L1 + L2 | 全 PR / push | ubuntu-latest 標準ランナー |
| `visual-qa.yml`（新設） | L3 Golden-file | 月次 nightly + PR ラベル `visual-qa` 時のみ | LibreOffice + Noto フォント同梱コンテナ |

- L3 は **LibreOffice インストール + 日本語フォント（Noto Sans CJK JP、Noto Serif CJK JP）をベイクしたコンテナイメージ**を GHCR で公開し、それを使用する（フォント解決差でのピクセル差を抑えるため）
- `visual-qa` ラベルが付いた PR では L3 を強制実行、その他 PR では L1 / L2 のみで高速マージを優先
- nightly 結果は SSIM 平均値・failure 件数を Slack `#pptmaker-qa` に投稿

### 8.6 メトリクス

CI 実行とは別に、本番系から以下のメトリクスを収集する。

| メトリクス | 定義 | 収集先 |
| --- | --- | --- |
| Placeholder leak 率 | 漏れ件数 / 生成スライド総数 | CloudWatch custom metric |
| Overflow 率 | Slot / Collision 違反件数 / 生成スライド総数 | CloudWatch custom metric |
| SSIM 平均 | nightly Visual QA の全 slide 平均 | DynamoDB 時系列テーブル |

SSIM 平均の **7 日移動平均が週比で 0.01 以上低下**した場合、Slack にトレンド悪化アラートを送出する。フォント更新や LibreOffice バージョンアップに伴う回帰を早期検知する目的。

### 8.7 段階導入

一度に全層を導入すると運用負荷が高いため、以下の順で段階導入する。

| フェーズ | 内容 | 完了条件 |
| --- | --- | --- |
| Step 1 | Placeholder guard 汎用化（既存 `test_layout_renderer.py:118-132` を置換） | `TemplateProfile.placeholder_defaults` 生成、全テンプレで leak 0 |
| Step 2 | Slot bounds / shape collision の静的検査 | `app/render/qa/overflow.py` 実装、CI 緑 |
| Step 3 | Golden file 雛形 3 ケース | `baseline_16_9`, `baseline_4_3`, one figure ケースで SSIM ≥ 0.98 |
| Step 4 | Golden 網羅拡大 + SSIM 閾値チューニング | 全 5 ケース運用、誤検知率 < 5% |
| Step 5 | Nightly 運用化、Slack 通知 | `visual-qa.yml` 月次稼働、メトリクス emit 開始 |

Step 1・2 は 2 スプリント以内で完了させ、Step 3 以降はテンプレ追加と連動して順次拡張する。

---

## 9. マイルストーン分割

Phase 2 は単一のスプリントではなく、依存関係と並走可能性を考慮した 5 つのマイルストーンに分割する。引き継ぎメモの指示に従い、Slot 認識を基盤として Figure 拡張と画像スロットを並走、その後テーマ継承、最後に Visual QA で締める。

### 9.1 Phase 2.1 — Slot 認識基盤（約 3 週間）

TemplateProfile を固定 body_area 前提から slot ベースに作り替える。全ての後続マイルストーンの前提となる基盤フェーズ。

**成果物**
- `app/render/theme_loader.py`（theme1.xml パーサ）
- `app/render/slot_extractor.py`（p:sp/p:ph 抽出器）
- `TemplateProfile v1.1` スキーマ（`layouts[].slots` を追加）
- 既存 TemplateProfile レコードの遅延マイグレーション

**完了条件**
- 社内標準 3 テンプレ（紫 16:9 / 白 4:3 / ダーク 16:9）で slot 抽出が人手検収と一致
- 既存 `tests/integration/test_e2e_flow.py` が無改変で緑のまま
- `FF_SLOT_RENDER=OFF` で Phase 1 と pixel diff 0

### 9.2 Phase 2.2 — Figure カタログ拡張（約 4 週間）

7 種から 20 種へ拡張。2.1 の slot API が固まってから着手するが、純粋に新規追加の renderer は 2.1 終盤から並走可。

**成果物**
- 13 種の新 FigureRenderer: `matrix` / `pyramid` / `org_chart` / `gantt` / `swot` / `kpi` / `quote` / `image_slot` / `icon_list` / `process_flow` / `timeline_v2` / `comparison_table` / `stat_grid`
- `schemas.py` の `FigureType` Literal を動的合成（renderer 登録から列挙を生成）
- `blueprint_system.txt` からハードコード列挙・skeleton 例を除去し、レジストリから生成関数化
- 各 figure_type の eval ケースを 2 件ずつ追加（計 26 ケース）

**完了条件**
- 20 種すべてで smoke test（LibreOffice 変換まで成功）緑
- 既存 7 種は `tests/golden/phase1/` に対して pixel diff 0
- blueprint_system.txt を更新しても LLM 出力の figure_type 不採用率が 5 % 以下

### 9.3 Phase 2.3 — 画像スロット（約 3 週間）

2.1 の slot 基盤上に画像配置を実装。2.2 と並走可。

**成果物**
- `ImageAsset` テーブルと storage レイヤ
- 画像 API 3 エンドポイント: `POST /projects/{id}/images/presign` / `POST /projects/{id}/images/commit` / `DELETE /projects/{id}/images/{asset_id}`
- `app/render/pptx_assembler.py` に `<p:pic>` 埋め込みと `[Content_Types].xml` / `_rels` 更新
- fit モード 4 種: `cover` / `contain` / `fill` / `fit_width`

**完了条件**
- cover / contain / fill / fit_width 各 1 例が golden（SSIM ≥ 0.98）で合格
- 10 MB 上限・MIME 検査（image/png, image/jpeg のみ）がテストで fail ケース含め動作
- presigned URL の TTL（15 分）超過で commit が 400 を返す

### 9.4 Phase 2.4 — テーマ継承（約 2 週間）

2.1 で読み込んだ theme1.xml を Palette 生成に繋ぎこむ。

**成果物**
- `theme_loader.py` の clrScheme / fontScheme 抽出
- `Palette.from_theme(theme)` 分類メソッドと既存 `DEFAULT_PALETTE` の fallback 化
- ラテン文字 / 東アジア文字のフォント mapping 表
- feature flag `FF_THEME_INHERITANCE` と per-template `theme_overrides`

**完了条件**
- 紫テンプレ以外の社内テンプレ 2 種で accent1 / accent2 が出力 `solidFill` に反映
- 指定フォントがホストに未インストールのとき、fallback（Noto Sans JP）に切替わる
- `FF_THEME_INHERITANCE=OFF` で Phase 1 配色と完全一致

### 9.5 Phase 2.5 — Visual QA（約 3 週間）

L2 / L3 QA とゴールデン運用、CI 組込み。全マイルストーンの品質ゲート。

**成果物**
- L2 ガード: `placeholder_guard` / `overflow_detector` / `collision_detector`
- L3 golden: 5 ケース（16:9 日本語 / 16:9 英語 / 4:3 日本語 / 画像込み / 全 figure 巡回）
- GitHub Actions `visual-qa-nightly` ジョブ
- Slack Webhook による SSIM レポート通知

**完了条件**
- nightly で golden 5 ケースが SSIM ≥ 0.98 で緑
- placeholder テキスト露出を人為的に混入させた PR で CI が赤
- SSIM レポート（diff 画像リンク付き）が #pptmaker-qa に到達

### 9.6 依存関係図

```
          [2.1 Slot 認識]
             │
     ┌───────┴────────┐
     ▼                ▼
[2.2 Figure 拡張]  [2.3 画像スロット]
     │                │
     └───────┬────────┘
             ▼
       [2.4 テーマ継承]
             │
             ▼
        [2.5 Visual QA]
```

2.2 と 2.3 は slot API 合意後に並走可。2.4 は色/フォント層のみで独立だが、slot 境界に色を流すため 2.1 完了待ち。2.5 は他 4 つの成果物を対象とするため最後。

### 9.7 総工数目安

| Phase | 期間 | 主担当 | 依存 |
|---|---|---|---|
| 2.1 | 3w | Render | なし |
| 2.2 | 4w | Render + LLM | 2.1 |
| 2.3 | 3w | Render + API | 2.1 |
| 2.4 | 2w | Render | 2.1 |
| 2.5 | 3w | QA / Infra | 2.2–2.4 |

- 直列換算: 15 週
- 2.2 と 2.3 の並走、2.4 の早期着手込みで **12–13 週**を目安
- バッファ（外部依存・レビュー待ち）は各マイルストーン内に 15 % 内包

---

## 10. 受入基準

Phase 2 完了判定は以下 9 条件の全充足とする。引き継ぎメモの 4 条件を正式化し、回帰・画像・テーマの実装条件に加え、§3.2 のコンサルスタイル規範（headline_message / grid alignment）の実装条件を含めた。

> **Phase 2 完了条件** — 15 スライド blueprint でテンプレ 6 ページを slot 指定どおりに使い切り、placeholder テキスト非露出、4:3 / 16:9 両対応、テーマ色継承。

| # | 基準 | 検証 | 測定タイミング |
|---|---|---|---|
| 1 | 15 枚 blueprint が 6 ページテンプレを指定どおり使い切る | 統合テスト `tests/integration/test_e2e_15slide_6page.py`: `SlideSpec.template_slide_index` の分布がテンプレ定義と一致、未使用ページゼロ | CI（PR ごと） |
| 2 | Slot 指定が renderer に反映され、body_area 固定ではない | 各 `slot.rect` と出力 shape の `a:off/a:ext` が ±1 EMU 以内で一致することを L2 QA で検査 | CI（PR ごと） |
| 3 | placeholder テキストが出力 pptx に 1 箇所も残らない | §8.2 Placeholder guard 汎用版が全 slide で fail ゼロ、NG 文字列リスト（"ここに…" "Lorem" 等）との突合 | CI（PR ごと） |
| 4 | 4:3 テンプレでも崩れない | `tests/golden/baseline_4_3/` が SSIM ≥ 0.98、12192000×6858000 固定仮定が §4 の slide size 動的化で解消 | nightly |
| 5 | テーマ色継承が効いている（紫以外で色が変わる） | `tests/integration/test_theme_inheritance.py`: theme.xml から抽出した accent1 / accent2 の値が出力 `solidFill` に現れる | CI（PR ごと） |
| 6 | 既存 7 figure_type のバイナリ互換が保たれる | `tests/golden/phase1/` に対する pixel diff 0 の回帰テスト | CI（PR ごと） |
| 7 | 画像 slot cover / contain / fill / fit_width が正しく動く | §6.5 golden 4 ケース（SSIM ≥ 0.98）+ アスペクト計算ユニットテスト | nightly + リリース前手動 |
| 8 | `SlideSpec.headline_message` が三層（LLM 出力スキーマ・DB・描画）で必須扱いになる | `tests/integration/test_headline_required.py`: 欠落 / タイトル再記述 / 体言止め のいずれも 422、既存 blueprint は migration 時に自動補完または warning | CI（PR ごと） |
| 9 | Grid alignment 警告が機能する | `tests/unit/test_grid_alignment.py`: 12 カラム基準線から逸脱する slot を含むテンプレで §8.3 の Warn がレポートに現れ、整合するテンプレでは出現しない | CI（PR ごと） |

**追加の非機能条件**
- p95 レンダリング時間が Phase 1 比 +20 % 以内（slot 解決・theme 解決のオーバヘッド）
- メモリピーク +15 % 以内
- Feature flag 全 OFF での Phase 1 互換を毎リリース前に手動確認

---

## 11. 既存コードへの影響と移行計画

### 11.1 影響ファイル一覧

| ファイル | 変更 | Phase |
|---|---|---|
| `app/render/shapes.py:28-45` | Palette を theme 由来にデフォルト化、`DEFAULT_PALETTE` は fallback 扱い | 2.4 |
| `app/render/layout_renderer.py:17` | `DEFAULT_BODY_AREA` を廃止（fallback のみ残す） | 2.1 |
| `app/api/models/schemas.py:16-24` | `FigureType` Literal の動的合成、`slots` フィールド追加 | 2.1, 2.2 |
| `app/api/prompts/blueprint_system.txt:14-52` | ハードコードされた figure_type 列挙と skeleton を生成関数化 | 2.2 |
| `app/api/services/template_registry.py` | slot 抽出の追加、`design_tokens` 充填 | 2.1, 2.4 |
| `app/api/services/blueprint_builder.py` | sanitizer を slot 対応に拡張 | 2.1 |
| `app/render/figure_renderers/*.py` | 13 新規追加、既存 7 は base class 変更時のみ修正 | 2.2 |
| `app/render/pptx_assembler.py` | `<p:pic>` 追加、`[Content_Types].xml` 更新 | 2.3 |
| `app/api/routers/projects.py` | 画像 API 3 エンドポイント追加 | 2.3 |
| `app/render/preview.py` | 変更なし（LibreOffice 変換層はそのまま） | — |
| `tests/` | `golden/` 配下、`qa/` 配下の拡充 | 2.5 |

### 11.2 DB マイグレーション

- `TemplateProfile.layouts` JSON スキーマ v1 → v1.1（`slots: SlotDef[]` を追加）
- 過去データは**起動時に遅延マイグレート**: `layouts[].slots` 欠損を検知したら該当テンプレから再抽出し保存
- `ImageAsset` テーブルは新規追加（破壊的変更なし）
- 既存 projects への影響は「blueprint 再生成不要、render 時にテンプレ参照で解決」

### 11.3 Feature flag

| Flag | 初期値 | 解除タイミング |
|---|---|---|
| `FF_SLOT_RENDER` | OFF | 2.1 安定確認後（社内テンプレ 3 種で 1 週間エラーなし） |
| `FF_THEME_INHERITANCE` | OFF | 2.4 完了後（2 テンプレで配色一致確認） |
| `FF_IMAGE_SLOT` | OFF | 2.3 完了後（全 fit モード golden 緑） |

両フラグが OFF のとき、Phase 1 挙動に完全互換であることをリグレッションテストで保証する。

### 11.4 ロールバック戦略

- いずれの flag も OFF に戻せば旧挙動に復帰
- DB 追加カラム（`slots` / `ImageAsset`）は残置しても害なし
- 緊急時はデプロイ戻しではなく flag OFF を一次対応とする

---

## 12. 将来拡張（Phase 3 以降）

Phase 2 はテンプレ忠実度・図表網羅性・QA の 3 軸を埋める回と位置づける。これら 3 軸が揃うと、社内限定運用から社外案件参考アーキテクチャへと足場の位置付けが変わる。Phase 3 以降はプラグイン開放と多モーダル、そして協調編集が主軸となる。

| 項目 | Phase | 備考 |
|---|---|---|
| テナント独自プラグイン（サンドボックス実行） | 3 | `04_template_and_plugin.md §7.3` |
| 画像生成 AI 連携 | 3 | Stable Diffusion / Claude 画像入力 |
| pptx 以外の出力（Google Slides / Keynote / HTML 配信） | 3–4 | Google Slides API / Keynote は iWork Archive |
| 自動テンプレ A→B マイグレーション | 3 | slot 対応付けの LLM 支援 |
| スライド単位の同時編集（OT/CRDT） | 4 | `SlideForge_概要設計書 §1.3` で明示対象外 |
| デザイナ AI レビュー（LLM による QA） | 3 | §8 のヒューリスティックを LLM 判定で補強 |

Phase 2 の完了は単なる機能追加ではなく、「テンプレート表現力の天井を撤廃し、品質をコードで守る」というプロダクト姿勢の宣言である。ここで確立された slot / theme / QA の三位一体が、Phase 3 のプラグイン開放におけるサンドボックス境界・互換性契約・レビュー基盤の土台として再利用される。

---

**本文書に関する問い合わせ**
DXデザインシステム株式会社
pptmaker 開発チーム
