# SlideForge

テンプレート駆動型の AI スライド生成システム。Claude API で骨格を生成し、コーポレートテンプレート準拠の `.pptx` を自動レンダリングします。Phase 1 は社内利用向けにサーバーレス最小構成で実装しています（`docs/SlideForge_概要設計書.md` §3）。

## リポジトリ構成

```
.
├── README.md
├── Makefile
├── pyproject.toml
├── app/
│   ├── api/            # FastAPI + Mangum（Lambda 用 API）
│   ├── render/         # Lambda Container（LibreOffice + python-pptx）
│   └── web/            # Next.js (App Router, static export)
├── infra/              # AWS CDK (Python) — Phase 1 単一アカウント構成
│   ├── app.py
│   ├── stacks/         # Pipeline / Data / App / Observability
│   ├── stages/
│   └── bootstrap/      # GHA OIDC 用 IAM ポリシー雛形
├── prompts/            # LLM プロンプト（プロジェクト運用用・後述）
├── evals/              # LLM-as-a-Judge による評価ハーネス
├── tests/              # unit / integration
├── scripts/            # PoC スクリプト（参考資産として保持）
├── outputs/            # PoC 成果物（.pptx / .pdf）
├── docs/
│   ├── SlideForge_概要設計書.md
│   ├── 01_prompt_engineering.md
│   ├── 02_ui_ux_design.md
│   ├── 03_ops_and_testing.md
│   ├── 04_template_and_plugin.md
│   ├── 05_security_compliance.md
│   ├── 06_business_plan.md
│   └── bootstrap.md        # AWS 初回セットアップ Runbook
└── .github/workflows/  # CI（GHA）
```

## ドキュメント

- 概要設計：`docs/SlideForge_概要設計書.md`
- 詳細設計：`docs/01_prompt_engineering.md` 〜 `docs/06_business_plan.md`
- **AWS 環境を初めて立ち上げる方へ**：`docs/bootstrap.md`

## クイックスタート（ローカル）

```bash
# 1. すべての依存をインストール
make install-api
make install-render
make install-infra
make install-web

# 2. テスト
make test-unit

# 3. API をローカル起動
cd app/api && source .venv/bin/activate
ENV=local uvicorn main:app --reload --port 8000
# → http://localhost:8000/docs で Swagger UI

# 4. Web をローカル起動
cd app/web && npm run dev
# → http://localhost:3000

# 5. Render Lambda Container をビルド
make build-render

# 6. CDK synth
make synth
```

## 初回デプロイ

**`docs/bootstrap.md`** を上から順に実行してください。所要 1〜2 時間。
最後の `make deploy-pipeline` 実行後、main への PR merge で自動的に Prod へデプロイされます（Phase 1 は単一ステージ、Stg は Phase 2 で新設）。

## 外部サービスからの呼び出し方（External Integration API）

`report_bot` のような外部サービス（Cloud Run / Cloud Functions など）から、Cognito の **client_credentials grant** を使って `POST /api/v1/external/slides` を叩くと、マークダウンを渡すだけで一発でスライドが生成できます。Web UI のステップ毎呼び出し（project → blueprint → render → export）をサーバ側で完結させたエンドポイントです。

### エンドポイント

```
POST <ApiEndpoint>/api/v1/external/slides
Authorization: Bearer <Cognito access token (scope: slideforge-api/slides:create)>
Content-Type: application/json

{
  "title": "週次レポート要約",
  "template_id": "DXDesignSystem",
  "report_markdown": "## 今週の出来事\n- ...",
  "source_url": "https://example.com/weekly/2026-05",
  "wait": true,
  "timeout_sec": 180
}
```

レスポンス：

```json
{
  "project_id": "9f...",
  "status": "done",
  "pptx_url": "https://...presigned...",
  "pdf_url":  "https://...presigned...",
  "preview_urls": ["https://...slide-01.jpg...", "..."]
}
```

`wait=false` の場合は blueprint 生成のみ行い `status: "pending"` で即時返却。失敗時は HTTP 5xx ではなく `status: "error"` と `error` フィールドで返るので、呼び出し側は分岐しやすいです。

### 1) 認証情報の取得

CDK デプロイ後、`App-prod` スタックの CloudFormation Outputs に以下が出力されます：

- `M2MClientId` — Cognito app client id
- `M2MCredentialsSecretArn` — Secrets Manager の secret ARN（`client_id` / `client_secret` / `token_url` / `scope` を JSON で保持）
- `CognitoTokenUrl` — OAuth 2.0 トークンエンドポイント

呼び出し側（report_bot 等）は **Secrets Manager の secret ARN を Cloud Run 等のシークレットマウントに渡す** だけで認証情報を取り出せます。手元から確認するなら：

```bash
aws secretsmanager get-secret-value \
  --secret-id slideforge/prod/m2m-credentials \
  --query SecretString --output text
```

### 2) アクセストークン取得 → スライド生成 (curl サンプル)

```bash
# 認証情報をシェルに展開
eval "$(aws secretsmanager get-secret-value \
  --secret-id slideforge/prod/m2m-credentials \
  --query SecretString --output text \
  | jq -r '. as $s | "CLIENT_ID=\($s.client_id)\nCLIENT_SECRET=\($s.client_secret)\nTOKEN_URL=\($s.token_url)\nSCOPE=\($s.scope)"')"

# アクセストークン取得（5分間有効）
ACCESS_TOKEN=$(curl -s -X POST "$TOKEN_URL" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=$SCOPE" \
  | jq -r .access_token)

# スライド生成
curl -s -X POST "$API_ENDPOINT/api/v1/external/slides" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "title": "週次レポート要約",
        "template_id": "DXDesignSystem",
        "report_markdown": "## 今週の出来事\n- A\n- B\n- C",
        "wait": true
      }' \
  | jq
```

`API_ENDPOINT` は `App-prod` の `ApiEndpoint` 出力（または独自ドメイン）を利用してください。

### 3) 動作仕様メモ

- `template_id` は UUID 文字列でもテンプレートの **表示名** でも受け付けます（同名が複数あれば最新を選択）。報告 bot 側はテンプレート差し替え時もコード変更不要。
- 認証ミドルウェアは Web ユーザ用トークンと M2M トークンの両方を同じ user pool（同じ JWKS）で検証します。M2M トークンでも `/api/projects` 等の Web 用エンドポイントには `slides:create` scope だけでは到達できないので、外部サービスは `/api/v1/external/*` のみ叩く設計です。
- プロジェクトは呼び出し元 client_id を `owner_user_id` として記録します。Web UI の「自分のプロジェクト」リストには現れませんが、CloudWatch / DB から追跡可能です。
- `Idempotency-Key` ヘッダは Phase 1 では受理して無視（後方互換のためのフックのみ用意）。Phase 2 で重複排除を入れます。

---

# PoC 資産（参考）

以下は `scripts/` と `outputs/` に残されている PoC 段階の資産のドキュメントです。正式版（`app/`, `infra/`）は上記を参照。

## 事前準備（PoC スクリプト実行）

### 必要な環境
- Python 3.10+
- LibreOffice（`soffice`コマンド）：PDFレンダリング用
- Poppler（`pdftoppm`コマンド）：PDFから画像生成用
- Anthropic製のPPTX SKILL スクリプト群（`unpack.py` / `add_slide.py` / `pack.py`）

### 入力ファイル
- コーポレートテンプレート `.pptx`
  - 想定：表紙／目次／セクション扉／コンテンツ／会社概要／免責事項の6種レイアウトを含む

## 実行手順

### 1. テンプレートの解凍とスライド複製

```bash
python3 /path/to/pptx/scripts/office/unpack.py \
  DXDesignSystem_Template.pptx template_unpacked/

# セクション扉（slide3）を3つ複製 → 計4枚のセクション扉
for i in 1 2 3; do
  python3 /path/to/pptx/scripts/add_slide.py template_unpacked/ slide3.xml
done

# コンテンツ（slide4）を9つ複製 → 計10枚のコンテンツ
for i in 1 2 3 4 5 6 7 8 9; do
  python3 /path/to/pptx/scripts/add_slide.py template_unpacked/ slide4.xml
done
```

### 2. スライド並び順の調整

`template_unpacked/ppt/presentation.xml` の `<p:sldIdLst>` 要素を構成通りに並び替え。

### 3. テンプレートの正規化

```bash
python3 scripts/normalize_template.py
```

フォント（Yu Gothic → Noto Sans JP）と配色（濃紫 → 柔らかい紫、濃黒 → 濃グレー）を一括置換。

### 4. 図表生成（4パート順に実行）

```bash
python3 scripts/build_figures_part1.py
python3 scripts/build_figures_part2.py
python3 scripts/build_figures_part3.py
python3 scripts/build_figures_part4.py
```

### 5. パック＆出力

```bash
python3 /path/to/pptx/scripts/office/pack.py \
  template_unpacked/ \
  DXDesignSystem_Proposal.pptx \
  --original DXDesignSystem_Template.pptx
```

### 6. PDF化（任意）

```bash
soffice --headless --convert-to pdf DXDesignSystem_Proposal.pptx
```

## カラーパレット

`shape_lib.py` で定義している配色：

| トークン | 用途 | HEX |
|---|---|---|
| `purple` | メインアクセント（ラベンダー寄り） | `#8B7AB8` |
| `purple_lt` | 淡い紫 | `#D9D1E8` |
| `purple_dk` | 合計バー等の差別化用 | `#6B5C96` |
| `purple_bg` | 極淡紫背景 | `#F5F2F9` |
| `black` | 本文テキスト（実際は濃グレー） | `#3A3A42` |
| `dark` | サブテキスト | `#5E5C6A` |
| `muted` | ミュート文字 | `#9B98A6` |
| `border` | 罫線 | `#E8E6EC` |
| `bg_alt` | カード背景 | `#FAFAFB` |
| `amber` | プロジェクト型アクセント（くすんだ金） | `#C4A05C` |
| `green` | 月額顧問アクセント（くすんだ緑） | `#5E9B7F` |

## 図表タイプと対応スライド

| 図表タイプ | 採用スライド | 実装ファイル |
|---|---|---|
| 表（交互配色＋ピルアクセント） | slide10（ご依頼事項マッピング） | part1 |
| 3カラムカード＋論点リスト | slide11（現状理解） | part1 |
| 2カラム（ねらい＋成果物）＋費用ボックス | slide12（統合DB設計） | part2 |
| 2x2マスタカード＋方針バッジ | slide13（共通マスタ） | part2 |
| 左右比較＋5項目チェックリスト | slide14（AIガイドライン） | part3 |
| 6ヶ月タイムラインバー | slide15（AI推進人材） | part3 |
| 表形式工数積み上げ＋シナリオ比較 | slide16（月額顧問工数） | part4 |
| 3カードプロジェクト＋合計バー | slide17（プロジェクト工数） | part4 |
| 費用内訳テーブル＋シナリオ大数字 | slide18（12ヶ月費用） | part4 |
| 5ステップタイムライン | slide4（Next Steps） | part4 |

## 重要な実装上の注意点（PoCで学んだこと）

### 1. EMU値は必ず整数化する

PowerPointは **EMU座標（1インチ=914400）** の値に**整数しか許容しない**が、LibreOfficeは浮動小数点も許容する。このためPython側で除算（`/`）を使うとfloat値がXMLに埋め込まれ、**LibreOfficeでは正常表示されてもPowerPointで開くと該当スライドがまるごと描画されない**という致命的バグが発生する。

対策として `shape_lib.py` 内の全shape生成関数（`rect_shape`, `rect_outline`, `text_box`, `text_box_multi`, `pill_label`, `h_line`）の入口で `_i()` ヘルパーによる整数化ガードを実装済み。システム化時はこのパターンを踏襲すること。

```python
def _i(v):
    """EMU値を必ず整数化（PowerPoint互換性）"""
    return int(round(v))

def rect_shape(sp_id, name, x, y, w, h, fill_color, ...):
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)  # ← 必須
    ...
```

### 2. XMLの直接操作依存

python-pptxライブラリよりも柔軟だが保守性は低い。ライブラリ化するなら抽象化レイヤーが必要。

### 3. 座標は全てEMU単位

`inch()`ヘルパーを通じて扱うが、計算途中の除算は要注意（上記の整数化問題）。

### 4. フォント指定は`Noto Sans JP`

PowerPoint側の環境に同フォントが入っていなければフォールバック。コンテナイメージ／配布先にフォント同梱を推奨。

### 5. テンプレートの初期スライド構成に依存

slide1=表紙、slide3=セクション扉、slide4=コンテンツ…という構成。別テンプレートを扱うにはレイアウト自動分類が必要。

### 6. LibreOfficeとPowerPointの差異を意識

PDFプレビューは LibreOffice 経由のため、見た目が合っていても PowerPoint で開くと壊れているケースがある。PoC完成後、PowerPoint での表示確認を必ず実施すること。

### 7. エラーハンドリングは最低限

システム化時はXMLの整形性チェック、リトライ、ロギング等を強化する必要あり。

## 開発経緯（抜粋）

1. pptxgenjsによるゼロからのPPTX生成（配色：Midnight Executive系）
2. コーポレートテンプレート持ち込み → pptxgenjs方式を断念
3. テンプレートスライドの複製＋テキスト置換方式に移行
4. 本文の中央寄せ／ラベル長過ぎによる折り返し等の微調整
5. 「テンプレートの本文プレースホルダーを削除し、図表XMLを挿入する」方式に進化
6. 黒背景 → 紫背景、濃紫 → 柔らかいラベンダーへの配色変更
7. **PowerPointで一部スライドが壊れる問題を発見 → EMU値の小数点問題が原因と判明 → 全関数に整数化ガードを追加**

## システム化における教訓のまとめ

本PoCで特に痛感した教訓：

| 教訓 | 理由 | 正式版での対応方針 |
|---|---|---|
| PDFプレビュー（LibreOffice）とPowerPoint実機の表示差異がある | EMU整数問題など、LibreOfficeは寛容な解釈をする | CI上でPowerPoint実機（M365/2019）での表示確認ステップを必ず組み込む |
| 座標計算で除算を使うとfloat化する | Python 3の `/` は常にfloat | コード規約で座標計算は必ず`_i()`で包む、もしくはEMU演算用クラスを作る |
| テンプレート差替え時のレイアウト順序依存 | slide番号で位置を特定していた | テンプレート解析で「レイアウト種別タグ」を付与し、論理名でアクセスする |
| 本文エリアの扱い（プレースホルダ削除＋図表挿入） | テンプレに「図・表を配置する前提」のスペースがあった | 図表レンダラーをレイアウト種別ごとに切り替えるパターンを標準化 |

詳細は本フォルダの `docs/SlideForge_概要設計書.md` 参照。
