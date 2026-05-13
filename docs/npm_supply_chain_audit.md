# npm サプライチェーン汚染対策 — 現状調査メモ

**作成日**：2026-05-13
**ブランチ**：`claude/npm-security-protection-mGASQ`
**スコープ**：本リポジトリ内で npm を利用する箇所（`app/web/`、CI/CD の `aws-cdk` 利用箇所）
**ステータス**：調査のみ（対策未実装）

---

## 1. 調査対象

| 領域 | パス | 用途 |
|---|---|---|
| Web フロント | `app/web/package.json` / `app/web/package-lock.json` | Next.js アプリ本体の依存関係 |
| CI（web ビルド） | `.github/workflows/ci.yml`（`web-build` ジョブ） | PR 時の typecheck / build |
| CI（CDK synth） | `.github/workflows/ci.yml`（`cdk-synth` ジョブ） | PR 時の `npx -y aws-cdk synth` |
| Deploy | `.github/workflows/ci.yml`（`deploy` ジョブ） | `npm install -g aws-cdk cdk-assets` |

リポジトリ全体で `.npmrc` / `dependabot.yml` / `renovate.json` は **存在しない**（`find` で確認済み）。

---

## 2. 現状できていること

1. **ロックファイルのコミット**：`app/web/package-lock.json`（225 KB）がコミット済み。バージョン解決はロックファイルで固定されている。
2. **CI で `npm ci` 使用**：`ci.yml:58-62` でロックファイル存在時は `npm ci` を実行（ロックファイル準拠インストール）。
3. **`private: true`**：`app/web/package.json:4` で誤公開を防止。

---

## 3. ギャップ（未対策の項目）

### 3.1 既知脆弱性チェックなし
- CI に `npm audit` / `npm audit signatures` のステップが無い。
- 既知 CVE が含まれるパッケージや、署名されていない/署名検証に失敗するパッケージがそのまま入る。

### 3.2 依存自動更新の通知系が無い
- `.github/dependabot.yml` 不在、Renovate も未設定。
- 悪意あるバージョンがリリースされた、または既存バージョンに脆弱性が判明しても、メンテナに通知されない。

### 3.3 postinstall スクリプトが無制限に実行される
- `.npmrc` に `ignore-scripts=true` 等の設定が無い。
- npm マルウェアの主要感染経路である `postinstall` / `preinstall` が、依存ツリー全体で無条件に走る。

### 3.4 グローバル install / npx でバージョン未固定
- `ci.yml:134`：`npm install -g aws-cdk cdk-assets`（バージョン無し → 常に latest）
- `ci.yml:83`：`npx -y aws-cdk synth`（`-y` で確認スキップ、初回は latest を取得）
- **本番デプロイの実行系**にあたるため、ここが汚染されると AWS 環境への影響が直撃する。

### 3.5 Dependency Review Action 未導入
- PR で新規依存が追加された際に、ライセンス・既知脆弱性をブロックする `actions/dependency-review-action` が無い。

### 3.6 npm 本体 / Node のバージョン未固定
- `package.json` に `engines` / `packageManager` の指定が無い。
- ワークフローでは `actions/setup-node@v4` の `node-version: '20'` のみ（マイナー/パッチは浮動）。

### 3.7 セマンティックバージョン範囲が広い
- `package.json:12-29` の依存はすべて `^` 範囲指定。
- ロックファイルが削除/再生成されると、`^` 範囲内の任意のバージョンに解決され得る（型定義・dev 依存も同様）。
- 例：`amazon-cognito-identity-js: ^6.3.12`、`zustand: ^4.5.2` 等。

### 3.8 SBOM / プロビナンス検証なし
- パッケージのプロビナンス（`npm publish --provenance` 由来の検証）を確認していない。
- SBOM（CycloneDX / SPDX）出力もしていない。

---

## 4. 推奨対策（優先度順、未着手）

| 優先度 | 対策 | 概要 | 実装箇所 |
|---|---|---|---|
| 高 | `.npmrc` に `ignore-scripts=true` | postinstall 経由のマルウェア実行を遮断 | `app/web/.npmrc` 新規 |
| 高 | グローバル `aws-cdk` / `cdk-assets` をバージョン固定 | `npm install -g aws-cdk@<X.Y.Z> cdk-assets@<X.Y.Z>` に変更 | `ci.yml:134` |
| 高 | `npx -y aws-cdk` をバージョン固定 | `npx -y aws-cdk@<X.Y.Z> synth` | `ci.yml:83` |
| 高 | Dependabot 有効化 | npm / github-actions / pip エコシステムを weekly 監視 | `.github/dependabot.yml` 新規 |
| 中 | CI に `npm audit --audit-level=high` | 高深刻度以上で失敗 | `ci.yml`（web-build に追加） |
| 中 | CI に `npm audit signatures` | 公式レジストリ署名の検証 | `ci.yml`（web-build に追加） |
| 中 | `actions/dependency-review-action@v4` | PR で新規依存をレビュー | `ci.yml`（PR トリガに追加） |
| 中 | `package.json` に `engines` / `packageManager` | npm / Node のバージョン固定 | `app/web/package.json` |
| 低 | SBOM 出力（CycloneDX 等） | リリースごとに成果物として保管 | `ci.yml`（deploy ジョブに追加） |
| 低 | `.npmrc` で `audit-level=high` / `fund=false` | 既定挙動の明示 | `app/web/.npmrc` |

---

## 5. 既存ドキュメントとの関係

- `docs/05_security_compliance.md` はアプリ自体の認証・テナント分離が中心で、**ビルドサプライチェーンには触れていない**。本ドキュメントはその空白を埋める位置付け。
- 対策を実装した際は、`docs/05_security_compliance.md` §（脆弱性管理セクション）への参照リンク追加も合わせて検討すること。

---

## 6. 次アクション

- [ ] 本ドキュメントをレビューし、実装する対策の範囲を確定
- [ ] §4 の「高」優先度から着手
- [ ] 実装後、本ドキュメントに「実装日 / 残課題」を追記
