# 提案書自動生成システム  概要設計書

**文書名**：AIスライド生成システム（仮称：SlideForge）  概要設計書
**版**：Draft v0.1
**作成日**：2026年4月16日
**作成者**：DXデザインシステム株式会社

---

## 1. システム概要

### 1.1 目的

今回のClaudeとの対話で行った「テンプレートに沿った提案書の自動生成」作業を、**社内で誰でも・何度でも・短時間で再現できる**仕組みとしてシステム化する。プロンプトエンジニアリングに習熟していないユーザーでも、定型的な提案書・報告書を高品質で量産できる状態を目指す。

### 1.2 位置づけ

- **第1フェーズ**：社内業務ツール（DXデザインシステム株式会社の営業・コンサル用途）
- **第2フェーズ**：顧客への社内ツール開発案件の参考アーキテクチャとして転用
- **第3フェーズ（任意）**：SaaSとして外部公開

### 1.3 スコープ

**対象**
- PowerPoint形式（.pptx）の提案書・報告書生成
- ユーザー提供のコーポレートテンプレート活用
- 図・表・カード・タイムラインなど定型レイアウトの自動配置
- LLMによる自然言語からの骨格案生成

**対象外（本バージョンでは）**
- スライドの動画・音声埋め込み
- 複数人による同時編集
- バージョン管理ツール（Git）との直接連携

---

## 2. ユーザーワークフロー

今回のClaudeとの対話プロセスを、5つのステップに整理する。

```
 ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
 │ 1.テンプレート │ → │ 2.スライド概要 │ → │ 3.プレビュー │ → │ 4.修正指示    │ → │ 5.アウトプット │
 │    登録       │   │    入力       │   │    確認       │   │  （反復）     │   │   生成        │
 └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
```

### Step 1. テンプレート登録

- ユーザーがコーポレートテンプレート（.pptx）をアップロード
- システムがテンプレートを解析し、「表紙／目次／セクション扉／コンテンツ／会社概要／免責事項」等のレイアウト種別を自動分類
- 分類結果をユーザーが確認・修正し、「テンプレートプロファイル」として保存
- カラーパレット、フォント、ロゴ位置などのデザイン要素を抽出しカタログ化

### Step 2. スライド概要入力

- ユーザーが以下のいずれかの方法で骨格を入力：
  - **自由記述モード**：「◯◯向けに、△△の提案書を作って」という自然言語
  - **構造化モード**：タイトル／セクション／各スライドの要旨をフォーム入力
  - **既存文書取込モード**：Markdown・Wordドキュメントをアップロードして自動構造化
- システム（LLM経由）が各スライドについて「レイアウト種別／図表タイプ／本文ドラフト」を提案

### Step 3. プレビュー確認

- 生成された.pptxをブラウザ上でプレビュー表示（各スライドを画像として表示）
- スライドごとに「レイアウト種別」「本文」「図表プレビュー」を確認可能
- 問題箇所をクリック／選択して修正対象に指定できる

### Step 4. 修正指示（反復）

- 自然言語で修正指示を入力（例：「もっと柔らかい色味に」「この表を3列に増やして」「slide5のタイトルを変更」）
- システムが指示をLLMで解釈し、該当部分のみ再生成
- 修正履歴を残し、任意の時点に巻き戻し可能
- Step 3とStep 4を満足するまで反復

### Step 5. アウトプット生成

- 最終版を.pptxでダウンロード
- 任意で .pdf／画像（.png）でも出力可能
- プロジェクトごとに「案件アーカイブ」として保存（再利用・流用可能）

---

## 3. システムアーキテクチャ

本システムはフェーズによって構成を変える方針。**Phase 1 はサーバーレス最小構成で立ち上げ、Phase 2 以降で段階的に拡張する**。

### 3.1 Phase 1 全体構成（最小構成）

```
┌────────────────────────────────────────────────────────────┐
│                  Frontend (Web UI)                          │
│   Next.js / React + TypeScript + Tailwind CSS               │
│   CloudFront は省略、S3 静的ホスティング + Cognito 認証     │
└─────────────────────────┬──────────────────────────────────┘
                          │ HTTPS / JSON
┌─────────────────────────▼──────────────────────────────────┐
│  API Gateway  →  Lambda (Python / FastAPI on Mangum)        │
│   - 軽量 API は同期 Lambda                                   │
│   - 重い処理は SQS → Lambda Container で非同期              │
└──────┬─────────────────┬──────────────────┬────────────────┘
       │                 │                  │
       ▼                 ▼                  ▼
┌────────────┐  ┌────────────────────┐  ┌─────────────┐
│ Claude API │  │ Render Lambda      │  │ RDS t4g.small│
│ (HTTPS)    │  │ (Container, 10GB) │  │ Single-AZ   │
│            │  │ LibreOffice 同梱   │  │ Postgres     │
│            │  │ + python-pptx     │  │             │
└────────────┘  └──────────┬─────────┘  └─────────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │       S3         │
                  │ templates /      │
                  │ projects /       │
                  │ outputs /        │
                  │ previews         │
                  └──────────────────┘

[Cognito] 認証、MFA 管理者のみ必須
[CloudWatch] Logs / Alarms（最小）
[Secrets Manager] Claude API Key
```

**設計方針**

- 単一 AWS アカウント、単一リージョン（ap-northeast-1）
- API は Lambda（FastAPI + Mangum）：月数千リクエストで従量課金が最小
- Render は Lambda Container 10GB に LibreOffice 同梱、重負荷時のみ Fargate Spot を暫定併用
- RDS db.t4g.small Single-AZ：50 ユーザーの規模に十分
- NAT Gateway / CloudFront / WAF / GuardDuty / CRR / ElastiCache は **Phase 1 では採用しない**
- 環境は **Prod 単一**（main マージ＝本番デプロイ）。Stg / Dev は Phase 2 で新設

Phase 1 簡略構成は**意図した技術的負債**であり、Phase 2 開始時点で再設計する（§3.3 参照）。

### 3.2 技術スタック（Phase 1）

| 層 | Phase 1 採用技術 | 理由 |
|---|---|---|
| フロントエンド | Next.js / React / TypeScript（S3 + Cognito 静的ホスティング） | 既存の当社技術スタック準拠 |
| バックエンド API | Python / FastAPI on AWS Lambda（Mangum 経由） | 従量課金、idle 時 $0 |
| 非同期処理 | SQS + Lambda Container（10GB 上限、LibreOffice 同梱） | Fargate 常駐の削減 |
| LLM | Claude API（Sonnet 4.6 標準、Opus 4.7 1M / Haiku 4.5 併用） | 高品質日本語、最新モデル |
| PPTX 生成 | python-pptx ＋ 独自 XML ビルダー | PoC 実績踏襲 |
| プレビュー | LibreOffice (soffice) + pdftoppm（Lambda Container 内） | PoC 動作確認済 |
| ストレージ | AWS S3（ファイル） / RDS db.t4g.small Single-AZ PostgreSQL（メタデータ） | Phase 1 では最小構成。Phase 2 で Aurora Serverless v2 に切替 |
| 認証 | Cognito（将来的に SSO 連携） | AWS 統一、社内展開容易 |
| インフラ | Lambda / API Gateway / SQS / S3（ECS / ALB / CloudFront は Phase 1 不採用） | 従量課金の恩恵を最大化 |
| CI/CD | GitHub Actions（CI） + AWS CodePipeline / CodeDeploy（CD） | 詳細は `03_ops_and_testing.md` §8 |

### 3.3 Phase 2 以降のアーキテクチャ拡張

以下は Phase 2 開始時点で段階的に導入する：

| 追加要素 | 導入タイミング | 理由 |
|---|---|---|
| Aurora Serverless v2 | Phase 2 | マルチ AZ、可用性要件 |
| ECS Fargate（API / Worker 常駐） | Phase 2 後半 | Lambda 15 分制限・コールドスタート問題が顕在化したら |
| ElastiCache Redis | Phase 2 | セッション / LLM 応答キャッシュ |
| CloudFront | Phase 2 | 顧客配信、地理分散 |
| WAF | Phase 2 | 外部攻撃面増加 |
| Stg 環境（独立 AWS アカウント） | Phase 2 | 本番前検証ステージを復活、CodePipeline のクロスアカウント構成に変更 |
| マルチアカウント（Dev/Stg/Prod 分離） | Phase 2 | 本番環境保護、監査分離 |
| GuardDuty | Phase 3 | SOC2 取得要件 |
| クロスリージョン DR | Phase 3 | SaaS SLA |
| Multi-Region Active-Active | Phase 4 以降 | 海外展開時 |

---

## 4. 主要コンポーネント

### 4.1 Template Registry（テンプレートレジストリ）

**責務**：アップロードされた.pptxテンプレートを解析し、再利用可能な「テンプレートプロファイル」として管理する。

**主要機能**
- PPTXの解凍・XML解析
- スライドレイアウトの自動分類（表紙／目次／セクション扉／コンテンツ／特殊スライド）
- デザインシステム抽出
  - カラーパレット（主色・副色・アクセント）
  - フォント（見出し／本文／欧文）
  - ロゴ位置・サイズ
  - プレースホルダー情報
- テンプレートプロファイルのCRUD

**データモデル（抜粋）**

```yaml
TemplateProfile:
  id: uuid
  name: "DXデザインシステム_v1"
  original_file_s3_path: "..."
  slide_layouts:
    - id: "cover"
      slide_index: 1
      placeholders: [title, subtitle, date, logo]
    - id: "toc"
      slide_index: 2
      placeholders: [index_items[5]]
    - id: "section_divider"
      slide_index: 3
      placeholders: [section_num, title, description]
    - id: "content"
      slide_index: 4
      placeholders: [title, body_area]
    # ...
  design_tokens:
    colors:
      primary: "#8B7AB8"
      secondary: "#D9D1E8"
      text: "#3A3A42"
    fonts:
      heading: "Noto Sans JP"
      body: "Noto Sans JP"
      mono: "Consolas"
```

### 4.2 Blueprint Builder（骨格ビルダー）

**責務**：ユーザー入力から「スライド骨格（Blueprint）」を構築する。

**処理フロー**
1. ユーザー入力（自然言語／フォーム／既存文書）を受け取る
2. Claude APIへプロンプト送信
3. LLMが返した構造化JSONをバリデーション
4. ユーザーに提示し、編集可能な骨格として保存

**骨格データモデル**

```yaml
Blueprint:
  id: uuid
  project_id: uuid
  template_profile_id: uuid
  slides:
    - index: 1
      layout: "cover"
      content:
        title: "DX推進・AI活用 ご提案書"
        subtitle: "..."
    - index: 4
      layout: "content"
      figure_type: "table"  # table / two_column / timeline / cards ...
      content:
        title: "ご依頼事項と契約形態の対応"
        table:
          headers: ["#", "依頼事項", "契約形態"]
          rows: [...]
```

**図表タイプの選択肢（初期リリース）**
- `table`：表組み
- `cards_grid`：カード格子（2x2、3x1 など）
- `two_column`：左右2カラム
- `timeline`：タイムライン
- `stat_callout`：数値強調
- `bullet_list`：構造化箇条書き
- `process_flow`：プロセスフロー
- `comparison`：対比（before/after）

### 4.3 Render Engine（レンダリングエンジン）

**責務**：Blueprintを実際の.pptxファイルに変換する。

**内部構造**
- `TemplateLoader`：テンプレートを解凍・スライド複製
- `LayoutRenderer`：各レイアウト種別に応じた描画
- `FigureRenderer`：図表タイプ別の描画（今回のshape_lib.pyが原型）
- `Packer`：XMLをパックして.pptxに戻す

**今回のPoCとの関係**

今回の作業で作成した以下の資産をそのまま組み込む：
- `shape_lib.py`（図形・テキスト生成関数群）→ `render_engine/shapes.py`
- `build_figures_part*.py` → `render_engine/figure_renderers/` 配下に分割
- `normalize_template.py` → `template_registry/normalizer.py`

### 4.4 Preview Service（プレビューサービス）

**責務**：生成された.pptxをブラウザで表示可能な画像に変換する。

**処理フロー**
1. 生成済み.pptxをS3から取得
2. LibreOffice（`soffice --convert-to pdf`）でPDF化
3. `pdftoppm` でスライドごとにJPEG化
4. S3に保存し、CloudFront経由で配信

**キャッシュ戦略**
- 同一Blueprintのハッシュに基づきキャッシュ
- 部分更新時は変更スライドのみ再生成

### 4.5 Revision Handler（修正ハンドラ）

**責務**：自然言語の修正指示を解釈し、Blueprint／テンプレートプロファイルを更新する。

**修正指示の類型**
| 種別 | 例 | 処理 |
|---|---|---|
| 色調調整 | 「紫を柔らかく」 | design_tokens.colors を更新 |
| テキスト修正 | 「slide5のタイトルを変更」 | Blueprintの該当フィールドを更新 |
| 構造変更 | 「表を3列に増やして」 | Blueprint.slides[n].content.tableを更新 |
| レイアウト変更 | 「カードを横並びに」 | figure_type または layout を変更 |

Claudeに以下のようなプロンプトを投げて、構造化された差分（JSON Patch形式）を受け取る：

```
User: 「この表を3列に増やして、列を追加」
↓
Claude: [{"op": "replace", "path": "/slides/3/content/table/headers", "value": [...]}]
```

---

## 5. データモデル（概要）

### 5.1 主要エンティティ

```
User ──┬─── Project ──┬── Blueprint ──── Slide
       │              │
       │              ├── RevisionHistory
       │              │
       │              └── Output (.pptx / .pdf)
       │
       └─── TemplateProfile
```

### 5.2 主要テーブル

| テーブル | 主キー | 主要カラム |
|---|---|---|
| users | id | email, tenant_id, role |
| tenants | id | name, plan, created_at |
| template_profiles | id | tenant_id, name, original_s3_path, design_tokens(JSON), layouts(JSON) |
| projects | id | tenant_id, name, template_profile_id, status |
| blueprints | id | project_id, version, slides(JSON), created_at |
| revisions | id | blueprint_id, instruction, diff(JSON), created_by, created_at |
| outputs | id | blueprint_id, format(pptx/pdf), s3_path, created_at |
| preview_images | id | blueprint_id, slide_index, s3_path |

---

## 6. API設計（抜粋）

| メソッド | パス | 概要 |
|---|---|---|
| POST | /api/templates | テンプレートアップロード＆プロファイル作成 |
| GET | /api/templates/:id | テンプレート詳細取得 |
| POST | /api/projects | プロジェクト作成 |
| POST | /api/projects/:id/blueprint | 骨格の生成（LLM呼び出し） |
| GET | /api/projects/:id/blueprint | 最新版の骨格取得 |
| POST | /api/projects/:id/render | .pptx生成＆プレビュー生成 |
| GET | /api/projects/:id/preview/:slide | スライドプレビュー画像取得 |
| POST | /api/projects/:id/revise | 修正指示適用 |
| GET | /api/projects/:id/history | 修正履歴一覧 |
| POST | /api/projects/:id/rollback/:version | 任意バージョンに巻き戻し |
| GET | /api/projects/:id/export?format=pptx | ダウンロード |

---

## 7. 非機能要件

| 項目 | 目標値 | 備考 |
|---|---|---|
| 骨格生成レイテンシ | ≤ 30 秒 | Claude API のレスポンス依存 |
| .pptx 生成レイテンシ | ≤ 20 秒（Phase 1） / ≤ 10 秒（Phase 2 以降） | Lambda コールドスタート許容 |
| プレビュー生成レイテンシ | ≤ 20 秒（Phase 1） | キャッシュなし前提 |
| 同時セッション数 | 最大 50（Phase 1） | Lambda 同時実行で吸収 |
| 可用性 | 99.0%（Phase 1、単一 AZ） / 99.5%（Phase 2） | 社内ツールのため緩め |
| RPO / RTO | RPO 24h / RTO 4h（Phase 1） | 自動スナップショット＋手動復旧 |
| データ保持 | プロジェクト 1 年 / テンプレ無期限 | 法的要件次第で変更 |

### セキュリティ

- 全通信TLS 1.3
- S3バケットはプライベート＋署名付きURL配信
- テンプレートおよびプロジェクトデータはテナント単位で隔離
- Claude APIキーはAWS Secrets Managerで管理、IAMロール経由でアクセス
- 将来的に顧客データを扱う場合はCognitoベースのRBAC、監査ログ（CloudTrail / アプリログ）を整備

---

## 8. 開発ロードマップ（目安）

| フェーズ | 期間 | スコープ |
|---|---|---|
| Phase 0：PoC整理 | 2週間 | 今回の資産を整理・ライブラリ化（shape_lib.py, build_figures_*.py） |
| Phase 1：MVP | 6〜8週間 | テンプレート登録／骨格入力／プレビュー／エクスポート（社内限定） |
| Phase 2：修正指示・履歴 | 4週間 | 自然言語修正ループ、巻き戻し機能 |
| Phase 3：UX改善 | 4週間 | プレビュー精度向上、テンプレート自動分類の精度改善 |
| Phase 4：SaaS化検討 | — | マルチテナント・課金・認証基盤の整備 |

---

## 9. リスクと論点

| # | リスク／論点 | 対応方針 |
|---|---|---|
| 1 | 複雑なテンプレートのレイアウト自動分類精度 | 初期はユーザー側で手動分類補正できるUIを用意 |
| 2 | 図表タイプの表現力限界 | プラグイン方式で新しい図表タイプを追加可能に設計 |
| 3 | Claude APIのコスト | テナントごとの利用量制限、キャッシュ活用 |
| 4 | レンダリング環境（LibreOffice）の保守性 | コンテナイメージで固定、定期的に検証 |
| 5 | 出力pptxのWindows PowerPointでの互換性 | CI段階で主要バージョン（2019／M365）で表示確認 |
| 6 | 日本語フォントのレンダリング差異 | 標準フォント（Noto Sans JP / Yu Gothic）をコンテナに同梱 |

---

## 10. 次のステップ

1. 本設計書のレビュー（技術・UX観点）
2. Phase 0の着手（今回のPoC資産の整理・ドキュメント化）
3. MVP要件の確定（特にUI要件・テンプレート登録フロー）
4. インフラ構成の詳細設計（ECS/RDS/Cognito構成、見積もり）
5. Phase 1キックオフ

---

**本件に関する問い合わせ**
DXデザインシステム株式会社
代表取締役　佐々木 拓
Web：https://sys.dx-design.co.jp
