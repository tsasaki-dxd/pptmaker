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
[ecr-push]       ── OIDC で AssumeRole → ECR push
                     - 常時: tag = commit SHA
                     - main 合流時のみ: tag = "prod" を追加 push
```

GHA は ECR に image を届けるまでが責務。以降は CodePipeline が ECR イベントで自走（§8.4）。**GHA から明示的に Pipeline を起動しない**（タグ分岐で制御する方が疎結合）。

### 8.3.1 OIDC Federation（静的キー不要）

GitHub Secrets に AWS の静的アクセスキーを置かない。GHA ジョブ毎に OIDC JWT を発行 → AWS STS が短命キー（1 時間）を返す方式を採用。

**GitHub 側に必要な設定**（Variables で十分、Secrets 不要）

| キー | 種別 | 値の例 |
|---|---|---|
| `AWS_ROLE_ARN` | Variable | `arn:aws:iam::<acct>:role/gha-slideforge-ecr-push` |
| `AWS_REGION` | Variable | `ap-northeast-1` |
| `ECR_REPOSITORY` | Variable | `slideforge/api` |

**AWS 側の 1 回セットアップ**

1. IAM OIDC Provider を追加（`token.actions.githubusercontent.com`、audience `sts.amazonaws.com`）
2. Role の Trust Policy で対象リポ・ブランチを限定（`sub` 条件で `repo:tsasaki-dxd/pptmaker:ref:refs/heads/main` 等）
3. Role の Permission は **ECR push 権限のみ**（`ecr:GetAuthorizationToken`, `ecr:PutImage`, レイヤー系）

**開発者の実感**

- ワークフロー上では `aws-actions/configure-aws-credentials@v4` に Role ARN と Region を渡すだけ
- 短命キーの取得・環境変数注入・失効はすべて action 内部で完結
- `AKIA...` や `SessionToken` を一度も触らない、Git に混入しえない
- 監査は CloudTrail の `AssumeRoleWithWebIdentity` イベントで追跡

**トラブル時の確認ポイント**

- AssumeRole 失敗 → Trust Policy の `sub` 条件（リポ名・ブランチ・環境の表記揺れ）
- 権限不足 → Role に紐付く IAM Policy（ECR のアクション／リソース）
- 長尺ジョブでキー期限切れ → ジョブ分割、1 時間以内に収める

### 8.3.2 イメージタグ設計

CodePipeline の起動は **ECR の image tag** で制御する。GHA 側がタグを書き分ける。

| トリガー | GHA が push するタグ | CodePipeline 起動 |
|---|---|---|
| PR（feature ブランチ） | `sha-<commit>` のみ | 起動しない |
| main 合流 | `sha-<commit>` + `prod` | 起動する（`prod` タグ検知） |
| hotfix（将来） | `hotfix-<date>` | 専用 Pipeline 起動 |

main 合流時だけ `prod` タグを追加 push する分岐を GHA で書く：

```yaml
- name: Push with SHA tag (always)
  run: docker push $REG/$REPO:${{ github.sha }}

- name: Promote to prod tag (main only)
  if: github.ref == 'refs/heads/main'
  run: |
    docker tag $REG/$REPO:${{ github.sha }} $REG/$REPO:prod
    docker push $REG/$REPO:prod
```

### 8.4 CodePipeline 側（CD）

Source は ECR ネイティブサポートを利用。CodePipeline 作成時に裏で EventBridge Rule が自動生成され、`prod` タグでの `PutImage` イベントを検知して Pipeline が自走する。**AWS は GitHub を監視しない**（GHA が image を ECR に届けた瞬間から AWS 側の話に切り替わる）。

```
Source: ECR Image (repo=slideforge/api, tag=prod)
        ※ 内部で EventBridge Rule → StartPipelineExecution
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
