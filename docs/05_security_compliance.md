# 05. セキュリティ・コンプライアンス設計書

**文書名**：SlideForge 詳細設計 — Security / Compliance
**版**：Draft v0.1
**参照**：`SlideForge_概要設計書.md` §3 / §7

---

## 1. 目的とスコープ

SlideForge の認証・認可、データ保護、テナント分離、監査、脆弱性管理、法令対応を扱う。

- Phase 1: 社内利用（DXデザインシステム株式会社）
- Phase 2: 顧客の社内ツール案件への転用
- Phase 3: SaaS として外部公開

扱うデータ：コーポレートテンプレート（社外秘）、提案書案件（顧客情報を含みうる）、LLM プロンプト・出力、監査ログ。

---

## 2. 脅威モデル（STRIDE）

| 脅威 | 例 | 対策 |
|---|---|---|
| Spoofing | 他テナントのユーザーになりすまし | Cognito + MFA、短期トークン |
| Tampering | API 経由での Blueprint 改ざん | RBAC、署名付き更新、監査ログ |
| Repudiation | 「やってない」主張 | 改ざん検知付き監査ログ、WORM 保管 |
| Information Disclosure | テンプレ・提案書の漏洩 | テナント分離、暗号化、アクセス最小化 |
| Denial of Service | アップロード/生成攻撃 | レート制限、ZIP Bomb 対策、WAF |
| Elevation of Privilege | 一般ユーザーが管理権限 | IAM 最小権限、機能別認可、ポリシー集約 |

主な想定攻撃者：
- A. 他テナントの正規ユーザー（権限外アクセス試行）
- B. 悪意のあるアップロードファイル
- C. LLM 経由での機密情報誘導
- D. 外部攻撃者（認証前／認証後）

---

## 3. 認証設計

### 3.1 基盤

AWS Cognito User Pool を採用。

- パスワード最小長 12、英数記号必須
- MFA：**管理者（Tenant Admin 以上）は必須**、一般ユーザーはオプション（将来必須化）
- SSO：SAML 2.0 / OIDC を Enterprise プランで提供
- セッション：アクセストークン 1 時間、リフレッシュトークン 30 日
- 失敗 5 回で 15 分ロックアウト

### 3.2 API 認証

- フロント → API: Cognito 発行の JWT を `Authorization: Bearer`
- サーバー間: IAM Role + SigV4
- 外部 Webhook: HMAC-SHA256 署名

---

## 4. 認可モデル（RBAC）

### 4.1 ロール

| ロール | 主な権限 |
|---|---|
| System Admin | 全テナント管理、監査ログ閲覧（社内運用者のみ） |
| Tenant Admin | 自テナントのユーザー / 設定管理 |
| Template Manager | テンプレート CRUD |
| Editor | プロジェクト CRUD、骨格生成・修正・エクスポート |
| Viewer | プロジェクト閲覧のみ |
| Auditor | 監査ログ閲覧（変更不可） |

### 4.2 権限マトリクス

| 操作 \ ロール | SysAdmin | TAdmin | TplMgr | Editor | Viewer | Auditor |
|---|---|---|---|---|---|---|
| テナント設定変更 | ✓ | ✓ | - | - | - | - |
| ユーザー管理 | ✓ | ✓ | - | - | - | - |
| テンプレ登録/編集 | ✓ | ✓ | ✓ | - | - | - |
| テンプレ閲覧 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| プロジェクト作成 | ✓ | ✓ | - | ✓ | - | - |
| 骨格生成 / 修正 | - | ✓ | - | ✓ | - | - |
| エクスポート | - | ✓ | - | ✓ | - | - |
| 監査ログ閲覧 | ✓ | ✓ | - | - | - | ✓ |

### 4.3 ACL

プロジェクト／テンプレートには個別 ACL（owner_id, shared_with[]）。ロール権限を満たしてもリソースに shared されていなければアクセス不可。

---

## 5. テナント分離方式

### 5.1 論理 vs 物理

| 方式 | コスト | 分離強度 | 採用 |
|---|---|---|---|
| 物理分離（テナント毎 DB/S3 バケット） | 高 | 最強 | Phase 3 の Enterprise 専用 |
| 論理分離（共有 DB + RLS + S3 Prefix） | 低 | 十分（RLS 適切運用時） | Phase 1 / 2 標準 |
| ハイブリッド | 中 | 強 | Phase 3 で検討 |

### 5.2 PostgreSQL RLS

```sql
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

CREATE POLICY projects_tenant_isolation ON projects
  USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- セッション開始時に必ずセット
SET app.current_tenant_id = '...';
```

アプリ層でも重ねて tenant_id 検証（多層防御）。

### 5.3 S3 Prefix

```
s3://slideforge-prod/
  tenants/
    {tenant_id}/
      templates/{tp_id}/...
      projects/{p_id}/
        blueprints/...
        outputs/...
        previews/...
```

IAM ポリシーで `${aws:PrincipalTag/tenant_id}` を `resource` の prefix と一致させる（ABAC）。

---

## 6. データ保護

### 6.1 保存時暗号化

| ストア | 方式 |
|---|---|
| S3 | SSE-KMS（テナント別カスタマーキー：Enterprise） |
| RDS Aurora | KMS 暗号化 |
| EBS | デフォルト暗号化 ON |
| ElastiCache | 保存時＋転送時暗号化 |

### 6.2 通信暗号化

- 全外部通信 TLS 1.3（TLS 1.2 は暫定許容、2026 Q4 で撤去）
- ALB ↔ ECS 間も ACM Private CA 発行の内部証明書で TLS
- Claude API 呼び出しは TLS 1.3

### 6.3 機密カラム

- `users.password_hash`（bcrypt）
- `tenants.saml_metadata`（KMS カラム暗号化）
- `secrets.*` は DB には置かず Secrets Manager 参照のみ

---

## 7. シークレット管理

- AWS Secrets Manager を正として管理
- ローテーション：
  - Claude API キー：90 日（手動キー切替＋両立期間 24 時間）
  - DB パスワード：60 日（自動）
  - 内部 JWT 鍵：30 日
- アプリはコンテナ起動時に IAM ロール経由で取得（ハードコード禁止）
- Git にシークレットが混入した場合の対応手順を Runbook 化（gitleaks を PR チェック）

---

## 8. アップロードファイルセキュリティ

### 8.1 PPTX 受入フロー

```
[1] Content-Type + マジックバイト検証（PK..）
[2] サイズ検証（≤ 50MB）
[3] ZIP ヘッダ解析：ファイル数 ≤ 2000、展開合計サイズ ≤ 500MB
[4] Zip Slip 検査：相対パス中に .. や 絶対パス不許可
[5] 拡張子ホワイトリスト：XML, rels, jpeg/png/emf/wmf, binary fonts
[6] .pptm 拒否（マクロ）
[7] XML 解析：XXE 無効化（defusedxml）、外部参照削除
    - oleObject, externalLink, p:extLst 内の未知要素を除去
[8] 画像は再エンコード（mime sniffing 回避）
[9] ClamAV スキャン
[10] 受入完了 → S3 に保存（SSE-KMS）
```

### 8.2 具体的なチェック

| 項目 | 実装 |
|---|---|
| Zip Slip | `Path(dest, name).resolve()` が `dest.resolve()` の子孫か |
| ZIP Bomb | `ZipInfo.file_size` 合計上限、個別ファイル上限 100MB |
| XXE | `defusedxml.ElementTree` 利用 |
| SSRF（画像 URL） | 外部 URL を許容せず、埋込画像は bytes でのみ受ける |
| マクロ | `ppt/vbaProject.bin` 検知で拒否 |

---

## 9. LLM セキュリティ

詳細なプロンプトインジェクション対策は `01_prompt_engineering.md` §10 参照。本書では **横断的な扱い** を定める。

- ユーザー入力は必ず User ロールで送信、System への連結禁止
- LLM に渡す前に PII 検知（氏名・メール・電話・クレジットカード）。ポリシーで許容範囲外は警告 / ブロック
- LLM 出力は XML 埋込前にエスケープ、script タグ等の混入検査
- LLM リクエスト／レスポンスのログは本文を取らず、メタデータ（トークン数、モデル、trace_id）のみ。本文取得はデバッグフラグ + 短期保管 + マスキング
- Anthropic の Data Usage Policy を契約で確認（デフォルトで学習に使用されない旨）
- プロンプトキャッシュは**テナント境界を越えない**（System Prompt に tenant_id を含めて分離）

---

## 10. 監査ログ

### 10.1 必須フィールド

```json
{
  "audit_id": "uuid",
  "ts": "2026-04-20T14:23:12Z",
  "actor": { "type": "user|system", "id": "...", "ip": "...", "ua": "..." },
  "tenant_id": "...",
  "action": "template.create|project.export|user.role.change|...",
  "target": { "type": "template|project|user", "id": "..." },
  "result": "success|failure",
  "diff": { ... },   // 変更の前後 (必要時)
  "metadata": { ... }
}
```

### 10.2 対象アクション

- 認証（login / logout / mfa_challenge）
- 権限変更（ロール付与/剥奪、ACL 更新）
- テンプレート CRUD
- プロジェクト CRUD、エクスポート
- LLM 生成（メタデータのみ）
- 設定変更（テナント設定、通知、API キー発行）
- 管理者による他テナント参照（緊急時のみ）

### 10.3 保管・改ざん検知

- S3 Object Lock（Governance モード）で WORM
- 保管期間 7 年（日本の商法・税法準拠）
- ハッシュチェイン：各レコードの SHA-256 を前レコードのハッシュと連結 → 改ざん検知
- 閲覧は Auditor ロールのみ、エクスポートは管理者承認

---

## 11. 個人情報・プライバシー

### 11.1 扱いうる PII

- 利用者の氏名・メールアドレス（ユーザーDB）
- 顧客担当者名（提案書内）
- 金額・契約情報（提案書内）

### 11.2 日本法対応

- 個人情報保護法
  - 利用目的の明示（プライバシーポリシー）
  - 第三者提供の制限（LLM ベンダーへの提供について利用者への通知／同意）
  - 安全管理措置（本書全体）
- データ所在：ap-northeast-1（東京）固定、越境転送は LLM 呼び出しのみ（ユーザー同意済）
- Phase 3 SaaS で GDPR 対象地域展開時は別途要件追加

### 11.3 データ主体の権利

- 開示請求：監査ログから該当ユーザーの行動一覧を抽出
- 削除請求：プロジェクト・ユーザー・テンプレのハード削除手順。監査ログは削除せず匿名化
- ポータビリティ：JSON エクスポート

---

## 12. アクセス制御・ネットワーク

### 12.1 VPC 構成

```
Internet
  ↓
[WAF] → [ALB] (Public subnet)
  ↓
[ECS Fargate] (Private subnet)
  ↓
[RDS] [ElastiCache] [S3 VPC Endpoint] (Private subnet / Gateway)
```

### 12.2 ルール

- ECS → Internet: NAT Gateway 経由で Claude API のみ許可（egress FQDN allowlist）
- Security Group：最小ポートのみ開放、default deny
- IAM：role 別に最小権限、`*` 禁止
- KMS キーポリシーで利用者制限

---

## 13. 脆弱性管理

| 項目 | 頻度 | ツール |
|---|---|---|
| 依存関係スキャン | PR毎 | Dependabot / Renovate |
| コンテナスキャン | build毎 | Trivy + ECR Scan |
| SAST | PR毎 | GitHub Advanced Security (CodeQL) |
| DAST | 週次 | OWASP ZAP（ステージング） |
| ペネトレーションテスト | Phase 1 内部 / Phase 3 外部 | 外部ベンダー |
| Secret Scan | PR毎 | gitleaks |

対応 SLA：CRITICAL 24 時間、HIGH 7 日、MEDIUM 30 日、LOW 90 日。

---

## 14. インシデント対応

### 14.1 フロー

```
検知（監視 / 通報）
  ↓
初動（on-call → Security Lead エスカレーション、15分以内）
  ↓
トリアージ（影響範囲特定、L1/L2/L3 判定）
  ↓
封じ込め（対象アカウント凍結 / 該当テナント隔離）
  ↓
根絶（脆弱性修正、認証情報ローテーション）
  ↓
復旧（サービス再開）
  ↓
事後レビュー（Postmortem、72 時間以内）
  ↓
関係者通知（法令上必要な場合 PPC / 顧客）
```

### 14.2 個人情報漏洩時

個人情報保護委員会への報告 3 〜 5 日以内の法定期限遵守、影響対象者への通知、弁護士チェック。

---

## 15. 法令・規制マッピング

| 法令/規格 | 要求 | 対応 |
|---|---|---|
| 個人情報保護法 | 安全管理、利用目的、第三者提供 | §11 |
| 電子帳簿保存法 | 帳票保管 7 年 | §10.3 |
| ISMS (ISO 27001) | 管理策 A.5–A.18 | Phase 2 取得目標 |
| SOC 2 Type II | Security / Availability / Confidentiality | Phase 3 取得目標 |
| NIST CSF | Identify/Protect/Detect/Respond/Recover | 全体で参照 |

---

## 16. リリース前セキュリティチェックリスト

### Phase 1 向け

- [ ] Cognito MFA 管理者必須 ON
- [ ] RLS 全テーブルで適用確認
- [ ] S3 バケット Public Block 全 ON、SSE-KMS 確認
- [ ] IAM ポリシーの `*` 許可がないこと
- [ ] アップロード検査 10 項目 OK
- [ ] 依存関係スキャン CRITICAL/HIGH ゼロ
- [ ] 監査ログのサンプル書込 OK / WORM 挙動確認
- [ ] Runbook が最新
- [ ] データフロー図 と 設計書 の整合

### Phase 2 追加

- [ ] 顧客データ取扱合意書テンプレ整備
- [ ] 顧客先 VPN / PrivateLink 対応確認
- [ ] ペネトレーションテスト合格

### Phase 3 追加

- [ ] SOC 2 Readiness 合格
- [ ] Bug Bounty プログラム整備
- [ ] データ所在 / 越境転送に関する利用規約更新
