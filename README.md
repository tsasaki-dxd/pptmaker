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

`report_bot` のような外部サービス（Cloud Run / Cloud Functions 等）が、Cognito の **client_credentials grant** を使って 2 本のエンドポイントを叩いてスライドを生成します。Web UI のステップ毎の呼び出し（project → blueprint → render → export）を **非同期 submit + polling** に圧縮した形です。

API Gateway HTTP API の 30 秒タイムアウトを超える blueprint LLM 呼び出し + render が中で走るので、同期版（旧 `wait=true`）は廃止し、polling 設計に移行しました。

### エンドポイント

```
POST <ApiEndpoint>/api/v1/external/slides             → 202 (submit)
GET  <ApiEndpoint>/api/v1/external/slides/{project_id} → 200 (poll)
```

両方とも `Authorization: Bearer <Cognito access token, scope=slideforge-api/slides:create>` 必須。エラーは HTTP 5xx ではなく **常に 200/202 + `status: "error"`** で返します（report_bot 側で HTTP コードとアプリエラーを混ぜずに済むよう統一）。

#### リクエスト/レスポンス スキーマ

```python
# POST body
{
  "title": "週次レポート要約",
  "template_id": "DXデザインシステム株式会社",     # UUID または display name (完全一致, 大文字小文字を区別)
  "report_markdown": "## 今週の出来事\n- ...",
  "source_url": "https://example.com/weekly/2026-05"  # optional, LLM への補助コンテキスト
}

# POST/GET response (両方で同じ shape)
{
  "project_id": "9f...",
  "status": "queued" | "rendering" | "done" | "error",
  "pptx_url":     null | "https://...presigned (24h)",
  "pdf_url":      null | "https://...presigned (24h)",
  "preview_urls": null | ["https://...slide-01.jpg", ...],
  "error":        null | "..."
}
```

### ステータス遷移

| status | 条件 | 次に取る行動 |
|---|---|---|
| `queued` | POST 直後 / blueprint worker 処理待ち（BlueprintJob.status=pending） | 3〜5 秒間隔で GET をリトライ |
| `rendering` | blueprint 完了済、render Lambda 実行中（project.status=rendering） | 同上 |
| `done` | render 完了（project.status=complete または partial） | `pptx_url` / `pdf_url` / `preview_urls` を取得 |
| `error` | blueprint 失敗 / render 失敗 / project 未発見 / テンプレート未発見 | `error` フィールドのメッセージを参照、再試行可否判断 |

```
                 POST /slides
                      │
                      ▼
                  ┌────────┐
                  │ queued │◄──── BlueprintJob.status=pending
                  └────┬───┘
       blueprint_worker│完了 + render SQS enqueue
                      ▼
                ┌──────────┐
                │ rendering│◄──── project.status=rendering
                └────┬─────┘
       render Lambda │完了
            ┌────────┴──────────┐
   complete │                   │ failed
            ▼                   ▼
        ┌──────┐            ┌──────┐
        │ done │            │ error│
        └──────┘            └──────┘
```

想定 polling: report_bot 側で **3〜5 秒間隔、最大 180 秒** で `done` / `error` を待つ。

### 1) 認証情報の取得

CDK デプロイ後、`App-prod` スタックの CloudFormation Outputs:

- `M2MClientId` — Cognito app client id
- `M2MCredentialsSecretArn` — Secrets Manager secret ARN（`client_id` / `client_secret` / `token_url` / `scope` を JSON で保持）
- `CognitoTokenUrl` — OAuth 2.0 token endpoint
- `ApiEndpoint` — `/api/v1/external/slides` をマウントしている API Gateway の URL（同一）

Cloud Run 側は Secrets Manager の secret を取得するか、GCP Secret Manager にコピーしてマウントしてください。手元から確認するだけなら:

```bash
aws secretsmanager get-secret-value \
  --secret-id slideforge/prod/m2m-credentials \
  --query SecretString --output text | jq
```

### 2) curl サンプル

```bash
# (a) 認証情報をシェルに展開
eval "$(aws secretsmanager get-secret-value \
  --secret-id slideforge/prod/m2m-credentials \
  --query SecretString --output text \
  | jq -r '. as $s | "CLIENT_ID=\($s.client_id)\nCLIENT_SECRET=\($s.client_secret)\nTOKEN_URL=\($s.token_url)\nSCOPE=\($s.scope)"')"

# (b) アクセストークン取得（既定で 1 時間有効）
ACCESS_TOKEN=$(curl -s -X POST "$TOKEN_URL" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=$SCOPE" \
  | jq -r .access_token)

# (c) スライド生成を submit (202 + status=queued + project_id を受け取る)
PROJECT_ID=$(curl -s -X POST "$API_ENDPOINT/api/v1/external/slides" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "title": "週次レポート要約",
        "template_id": "DXデザインシステム株式会社",
        "report_markdown": "## 今週の出来事\n- A\n- B\n- C"
      }' \
  | jq -r .project_id)

# (d) 完了まで polling
for i in $(seq 1 60); do
  RESULT=$(curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
    "$API_ENDPOINT/api/v1/external/slides/$PROJECT_ID")
  STATUS=$(echo "$RESULT" | jq -r .status)
  echo "poll $i: $STATUS"
  case "$STATUS" in
    done)  echo "$RESULT" | jq; break ;;
    error) echo "$RESULT" | jq; exit 1 ;;
  esac
  sleep 3
done
```

### 3) 動作仕様メモ

- `template_id` は UUID でも **表示名 (完全一致, 大文字小文字を区別)** でも可。同名が複数あれば最新を優先。曖昧マッチ (ilike / 部分一致) は事故防止のため不可 — 名前のタイポ / 半角全角揺れがあると `status: "error"` で素直に弾きます。
- 認証は Web ユーザトークンと M2M トークン両方を同じ user pool / JWKS で検証。M2M トークンの `slides:create` scope では Web 用エンドポイントは叩けないので、外部サービスは `/api/v1/external/*` のみ利用してください。
- 作成プロジェクトの `owner_user_id` は呼び出し元 client_id。Web UI の「自分のプロジェクト」には現れません。
- `Idempotency-Key` ヘッダは Phase 1 では受理して無視（夢の Phase 2 で本物の dedupe を実装する用のフック）。
- presigned URL の有効期限は 24 時間。`done` を観測した後は何度 GET しても毎回新しい URL が返るので、Chat 投稿のリトライにも対応できます。

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
