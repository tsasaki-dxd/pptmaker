# 03. 運用・テスト・CI/CD 設計書

**文書名**：SlideForge 詳細設計 — Ops / Testing / CI/CD
**版**：Draft v0.1
**参照**：`SlideForge_概要設計書.md` §3 / §4.3 / §7 / §9、`README.md` 実装上の注意点

---

## 1. 目的とスコープ

SlideForge の可用性・品質・保守性を支える運用側設計。ロギング、監視、テスト戦略、PowerPoint 互換性検証、CI/CD、障害対応を扱う。

---

## 2. SLI / SLO

| SLI | 定義 | SLO | 測定 |
|---|---|---|---|
| API 可用性 | 5xx 率 | 99.5% (30日) | ALB アクセスログ |
| 骨格生成成功率 | L1 正常完了 / 総呼出 | 98% | アプリメトリクス |
| .pptx 生成成功率 | レンダリング正常完了 | 99% | Render ジョブログ |
| プレビュー生成レイテンシ | p95 | ≤ 15秒 | ジョブメトリクス |
| 骨格生成レイテンシ | p95 | ≤ 30秒 | LLM クライアント計測 |
| PowerPoint 互換性 | 出力 pptx の PP 正常表示率 | 99% | CI + サンプリング目視 |

エラーバジェット：SLO 超過時は新機能開発を止め、信頼性改善を優先。

---

## 3. ロギング設計

### 3.1 形式

JSON 構造化ログを標準出力に。CloudWatch Logs で収集、30 日後 S3 アーカイブ。

### 3.2 必須フィールド

```json
{
  "ts": "2026-04-20T14:23:12.123Z",
  "level": "INFO",
  "service": "api",
  "trace_id": "abc123",
  "span_id": "def456",
  "tenant_id": "t_001",
  "user_id": "u_123",
  "project_id": "p_456",
  "blueprint_id": "bp_789",
  "event": "llm.blueprint.generated",
  "llm_model": "claude-sonnet-4-6",
  "llm_tokens_in": 2850,
  "llm_tokens_out": 2410,
  "llm_cache_hit_ratio": 0.72,
  "latency_ms": 18230
}
```

### 3.3 保持期間

- アプリログ: CloudWatch 30 日 → S3 IA 1 年 → S3 Glacier 7 年
- アクセスログ: 90 日
- 監査ログ: WORM S3（詳細は 05_security_compliance.md）

---

## 4. 監視・アラート

### 4.1 主要メトリクス

| カテゴリ | メトリクス | アラート閾値 | 通知先 |
|---|---|---|---|
| API | 5xx 率 | 5分平均 >1% | PagerDuty: on-call |
| API | レイテンシ p95 | >3秒 | Slack #slideforge-ops |
| LLM | 失敗率 | 5分平均 >5% | PagerDuty |
| LLM | コスト日次 | 予算 80% 到達 | Slack |
| Render | 失敗率 | 5分平均 >2% | PagerDuty |
| Queue | 滞留深さ | >100 件が10分継続 | PagerDuty |
| DB | 接続数 | >80% of max | Slack |
| S3 | 4xx 率 | >1% | Slack |

### 4.2 スタック

- AWS CloudWatch（基本メトリクス・ログ）
- Datadog（APM、分散トレース、ダッシュボード） — コスト許容内で採用
- PagerDuty（オンコール）

---

## 5. 分散トレーシング

- OpenTelemetry SDK を Next.js / FastAPI / Render Worker に導入
- 主要スパン: `http.request` → `llm.blueprint.generate` → `render.pptx.build` → `preview.image.generate`
- 伝播: W3C Trace Context (`traceparent` ヘッダ)
- 保存: Datadog APM（7日保持）、重要トレースは 90 日

---

## 6. テスト戦略

### 6.1 テストピラミッド

```
          /\
         /E2\           ~5%  : Playwright E2E
        /----\
       / VRT  \         ~10% : Visual Regression（pptx → png）
      /--------\
     / Integration\     ~25% : API + Render
    /--------------\
   /   Unit         \   ~60% : shape_lib, validation, EMU
```

### 6.2 ユニット

- 対象: `shape_lib.py` 相当の図形関数、バリデーション、EMU 演算
- 特に `_i()` 相当の整数化ガードを外した場合に壊れることを Test する（回帰防止）
- カバレッジ目標: 85%

### 6.3 結合

- API 層 + Render Engine の通し
- TemplateProfile モック / 実テンプレ両方
- LLM はモック（録画済みレスポンス再生）

### 6.4 E2E（Playwright）

シナリオ：
1. テンプレアップロード → プロファイル確認 → 保存
2. プロジェクト作成 → 骨格生成 → プレビュー確認
3. 修正指示（色・テキスト・構造）→ 差分適用
4. 履歴巻き戻し
5. .pptx エクスポート

### 6.5 ビジュアルリグレッション（VRT）

**PoC で最も痛手を負った領域なので重点**：

- 生成 .pptx を LibreOffice → PDF → PNG 変換
- 基準画像と pixel diff（閾値 0.3% まで許容）
- 新規テンプレ追加時はスナップショット更新
- `playwright-visual` or `reg-cli` で管理

### 6.6 LLM Eval

`01_prompt_engineering.md` §11 参照。CI で主要観点のみ実行、週次で全件実行。

---

## 7. PowerPoint 互換性 CI

PoC 教訓：LibreOffice では正常だが PowerPoint で壊れる事象が発生（EMU float 問題）。

### 7.1 静的検査（Lint）

実行時コスト低、PR ごとに必ず実行。

| チェック | 方法 |
|---|---|
| EMU 値が全て整数 | XML を xmllint → XPath で `@x @y @cx @cy` 抽出し float 検出 |
| Open XML Schema 適合 | `xmllint --schema` で pml.xsd 検証 |
| 禁止要素の混入 | `oleObject`, `externalLink`, `p:extLst`（既知の壊れパターン） |
| フォントリファレンス | 未インストールフォント警告 |
| 色参照 | 参照スキーム外の色 |

### 7.2 動的検査（Windows Runner）

夜次 / リリース前のみ、コスト高のため。

- GitHub Actions の `windows-latest` ランナー上で PowerShell + PowerPoint Interop
- 全スライドを画像化し、描画エラー / 欠損を検知
- 代替: Microsoft Graph API の PowerPoint レンダリング（将来検討）

### 7.3 チェックリスト（リリース前）

- [ ] Lint 緑
- [ ] VRT 差分ゼロ / 承認済み
- [ ] Windows Runner での描画検査緑
- [ ] サンプル 3 テンプレで実機 PowerPoint での手動確認（月次）

---

## 8. CI/CD パイプライン

### 8.1 方針：ハイブリッド構成（GHA for CI / CodePipeline for CD）

CI は **GitHub Actions**、CD は **AWS CodePipeline + CodeDeploy** に分離する。

| 責務 | 担当 | 理由 |
|---|---|---|
| PR 検証 / Lint / Unit / Integration | GitHub Actions | PR 連動、並列性、Marketplace 資産、高速 |
| Container build → ECR push | GitHub Actions（OIDC） | 静的キー不要、PR ビルドと共通化 |
| Visual Regression / LLM Eval | GitHub Actions | PR 連動、差分レビュー容易 |
| デプロイ承認・ステージ管理 | CodePipeline | 承認待ちが課金対象外、マルチアカウント統制 |
| ECS Blue/Green | CodeDeploy | AWS ネイティブ、無料、自動ロールバック |
| スモークテスト / ロングランチェック | CodeBuild (CodePipeline 内) | 長尺処理を GHA 分単位課金から切り離す |

### 8.2 コストの根拠

| 項目 | GHA | CodePipeline |
|---|---|---|
| 単価 | $0.008 / 分（Linux） | $1 / pipeline / 月 |
| 承認待ち時間 | **課金対象**（ジョブ保持中） | **無料** |
| ECS Blue/Green 待ち | 分課金で食いつぶす | CodeDeploy は無料 |

CD に長尺の待ち・承認を含めると GHA 分数を圧迫するため、CD 部分は CodePipeline に寄せる。

### 8.3 GitHub Actions 側（CI）

```
trigger: PR / push to main
  ↓
[lint]           ── ruff, mypy, eslint, tsc         (並列)
[unit]           ── pytest, jest                    (並列)
[pptx-lint]      ── 生成サンプル .pptx の静的検査   (並列)
  ↓
[integration]    ── docker-compose で API + Render 起動
  ↓
[build-container] ── Docker build, Trivy scan
  ↓
[visual-regression] ── reg-cli diff
[llm-eval]          ── prompts/evals 実行（main 到達時）
  ↓
[ecr-push]       ── OIDC で AssumeRole → ECR push（tag = commit SHA）
  ↓
[trigger-cd]     ── CodePipeline を ECR イメージタグで起動
```

**OIDC 設定**：GitHub → AWS IAM OIDC Provider を信頼、Role は `ecr:Put*` / `codepipeline:StartPipelineExecution` のみに最小化。

### 8.4 CodePipeline 側（CD）

```
Source: ECR Image (tag filter)
  ↓
[deploy-dev]     ── CodeDeploy / ECS Blue/Green（Dev アカウント）
  ↓
[smoke-dev]      ── CodeBuild（E2E 抜粋、ヘルスチェック）
  ↓
[approval-stg]   ── 手動承認（Slack 通知 + AWS Console 承認）
  ↓
[deploy-stg]     ── Staging
  ↓
[smoke-stg]      ── 本番相当 E2E、Windows PPT 互換（§7 の nightly を流用）
  ↓
[approval-prod]  ── 手動承認（複数人レビュー、変更影響サマリを添付）
  ↓
[deploy-prod]    ── Prod（CodeDeploy カナリア 10% → 100%）
  ↓
[post-deploy]    ── メトリクス自動監視（5分）、アラートで自動ロールバック
```

- Dev / Stg / Prod は **別 AWS アカウント**（CodePipeline のクロスアカウント実行）
- CodeDeploy の `CanaryDeploymentConfig` で段階リリース
- 失敗検知時は CodeDeploy が自動でターゲットグループを Blue 側に戻す

### 8.5 nightly ワークフロー

以下は PR に載せず、nightly の GHA スケジュールで実行：

- E2E 完全版（Playwright）
- Windows PowerPoint 互換テスト（§7）
- DAST スキャン（OWASP ZAP）
- 依存関係再スキャン（Renovate）

失敗時は Slack 通知 + GitHub Issue 自動起票。

### 8.6 並列化と所要時間目標

| Stage | 目標時間 |
|---|---:|
| GHA CI（PR）全体 | ≤ 12 分 |
| lint / unit / pptx-lint（並列最長） | ≤ 4 分 |
| integration | ≤ 3 分 |
| build + VRT | ≤ 5 分 |
| CodePipeline Dev → Prod（承認待ち除く） | ≤ 25 分 |

---

## 9. デプロイ戦略

### 9.1 Blue/Green（ECS Fargate + CodeDeploy）

- CodePipeline から CodeDeploy を起動し、ECS Service を Blue/Green 展開
- カナリア: `CodeDeployDefault.ECSCanary10Percent5Minutes` を採用（Prod）
- 新タスク 10% に 5 分通流 → メトリクス正常で 100% → 旧タスク 5 分温存 → 破棄
- ロールバック: CodeDeploy の CloudWatch アラーム連動で自動（30 秒以内に Blue 切戻し）
- Dev / Stg は `ECSAllAtOnce`（高速デプロイ）

### 9.2 DB マイグレーション（Alembic）

- 後方互換戦略：旧コード + 新スキーマで動作する中間状態を必ず経由
  1. カラム追加（nullable）
  2. 両方書き込みリリース
  3. バックフィル
  4. 新カラム必須化
  5. 旧カラム削除
- マイグレーションは常に先行、アプリリリースは後

### 9.3 フィーチャーフラグ

- LaunchDarkly or 自前の環境変数ベース
- プロンプト変更、新図表タイプ、LLM モデル切替に使用
- テナント別 ON/OFF

---

## 10. コンテナイメージ

### 10.1 構成

- ベース: `python:3.12-slim-bookworm`
- LibreOffice: `libreoffice-impress` 同梱（約 400MB）
- Poppler: `poppler-utils`
- フォント: Noto Sans JP / Noto Sans CJK JP / Yu Gothic (任意)
- Claude SDK: `anthropic`
- サイズ目標: < 1.2GB

### 10.2 Dockerfile 断片

```dockerfile
FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice-impress poppler-utils fonts-noto-cjk \
      fontconfig curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.lock /app/
RUN pip install --no-cache-dir -r requirements.lock
COPY . /app/
USER 10001
CMD ["python", "-m", "slideforge.worker"]
```

### 10.3 スキャン

- Trivy を CI に組み込み（CRITICAL / HIGH で fail）
- ECR Scan on Push を有効化
- 週次で依存更新 PR 自動生成（Dependabot / Renovate）

---

## 11. 障害対応

### 11.1 Runbook 章立て

- RB-01: テンプレ解析失敗
- RB-02: LLM タイムアウト
- RB-03: Render 失敗（XML 不正 / フォント欠落）
- RB-04: PowerPoint 互換検知
- RB-05: S3 書込失敗
- RB-06: DB 接続枯渇
- RB-07: LibreOffice 暴走（OOM）

### 11.2 RTO / RPO

| レベル | RTO | RPO |
|---|---|---|
| API | 15 分 | 5 分 |
| DB | 30 分 | 5 分（PITR） |
| S3 | 5 分 | 0（クロスリージョン） |

### 11.3 エスカレーション

```
L1: on-call engineer (15min)
  ↓ 解決不可なら
L2: service owner (30min)
  ↓
L3: CTO / 代表取締役（個人情報事故・重大障害）
```

---

## 12. キャパシティプランニング

- 同時ジョブ数: 初期 50（Phase 1）、Phase 3 で 500
- Render Worker は SQS キュー深さベースでオートスケール
  - target: 1 worker = 5 ジョブ同時処理、キュー深さ 20 超で +1 Worker
  - 最小 2 / 最大 50
- API は CPU 使用率 60% で +1、30% で -1
- RDS Aurora Serverless v2（ACU 2〜16 レンジ）

---

## 13. バックアップ / DR

- RDS: 自動バックアップ 30 日、PITR 有効
- S3: クロスリージョンレプリカ（ap-northeast-1 → ap-northeast-3）
- リストア演習: 四半期ごとに実施
- ディザスタリカバリ: 別リージョンに IaC で再構築可能な状態を維持

---

## 14. 運用ドキュメント

- Runbook: Notion or Confluence に集約、四半期レビュー
- Playbook: 定型作業（テナント追加、モデル切替、テンプレ緊急削除）手順
- SRE ダッシュボード: Datadog に SLI/SLO、LLM コスト、Render 成功率を集約
- オンコール: 週次ローテーション、ハンドオフ議事録を必須
