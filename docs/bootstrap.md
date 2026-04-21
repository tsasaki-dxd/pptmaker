# SlideForge 初回ブートストラップ Runbook（Phase 1）

**対象**：SlideForge の AWS 環境を初めてセットアップする運用担当者
**前提**：AWS アカウント 1 つ、管理者権限を保有、GitHub リポジトリの管理者権限を保有
**所要時間**：約 30 分（GHA ワークフロー実行時間含む）
**参照**：`docs/03_ops_and_testing.md` §8, §15 / `docs/SlideForge_概要設計書.md` §3

---

## 0. 方針

Phase 1 のブートストラップは **GitHub Actions のワークフロー `bootstrap.yml`** で実行します。
ローカルに AWS CLI / CDK をインストールする必要はありません。

ブートストラップ専用の IAM ユーザーを 1 つ作成し、その静的キーを GitHub Secrets に格納して一度だけ実行、完了後にそのキーは即座に失効させる運用です。以降の通常 CI/CD は OIDC Federation で静的キーなしに動きます。

---

## 1. AWS 側の準備（Console で 1 度だけ）

### 1.1 ブートストラップ用 IAM ユーザー作成

AWS IAM コンソールで以下を作成：

| 項目 | 値 |
|---|---|
| ユーザー名 | `slideforge-bootstrap` |
| アクセス方式 | プログラム的アクセス（アクセスキー） |
| 付与ポリシー | `AdministratorAccess`（ManagedPolicy） |

**⚠️ このユーザーはブートストラップ完了後に必ず削除する**。通常運用では使いません。

作成時に表示されるアクセスキー ID / シークレットアクセスキーを控える。

---

## 2. GitHub Secrets / Variables 設定

### 2.1 Secrets（ブートストラップ専用・実行後に削除）

GitHub リポジトリ → Settings → Secrets and variables → Actions → **Secrets** タブ：

| 名前 | 値 |
|---|---|
| `BOOTSTRAP_AWS_ACCESS_KEY_ID` | §1.1 で取得したアクセスキー ID |
| `BOOTSTRAP_AWS_SECRET_ACCESS_KEY` | §1.1 で取得したシークレットアクセスキー |
| `BOOTSTRAP_AWS_REGION` | `ap-northeast-1` |
| `ANTHROPIC_API_KEY` | Anthropic Console で発行した Claude API Key |

これら 4 つはブートストラップ後に**削除推奨**（§6）。

### 2.2 Variables（通常運用で使うので残す）

ブートストラップ完了**後**に手動で設定します（§5）。このタイミングでは設定しません。

---

## 3. ブートストラップ実行

### 3.1 ワークフロー起動

1. GitHub → Actions → **Bootstrap** ワークフロー
2. Run workflow → Branch: `main` → confirm 欄に `BOOTSTRAP` を入力
3. Run workflow ボタン

### 3.2 実行内容

ワークフローが以下を順に実行（すべて冪等）：

1. AWS 認証（Secrets の IAM キー）
2. IAM OIDC Provider（`token.actions.githubusercontent.com`）を作成
3. GHA 用 IAM Role `gha-slideforge-ecr-push` 作成（信頼ポリシーで当リポジトリに限定、権限は ECR push のみ）
4. ECR リポジトリ `slideforge/render` 作成
5. Secrets Manager に `slideforge/anthropic` を投入（`ANTHROPIC_API_KEY` を格納）
6. CDK Bootstrap（`CDKToolkit` スタック作成）
7. `SlideForgePipelineStack` をデプロイ

完了時に Job Summary に「次にやること」が表示されます。

### 3.3 所要時間

- Lint/Test 等はスキップ。CDK bootstrap と Pipeline Stack deploy で合計 10〜15 分目安

---

## 4. Verification（完了チェック）

ワークフローが ✅ で終了したら、以下も Console で確認：

- [ ] IAM → Identity providers に `token.actions.githubusercontent.com` が存在
- [ ] IAM → Roles に `gha-slideforge-ecr-push` が存在、Trust Policy に `repo:<owner>/pptmaker:*` が設定
- [ ] ECR → Repositories に `slideforge/render` が存在
- [ ] Secrets Manager に `slideforge/anthropic` が存在し値が入っている
- [ ] CloudFormation に `CDKToolkit` / `SlideForgePipelineStack` が CREATE_COMPLETE
- [ ] CodePipeline に `SlideForgePipeline` が存在

---

## 5. GitHub Variables を設定（通常 CI 用）

Job Summary に表示された内容を GitHub Variables に貼り付け。

GitHub → Settings → Secrets and variables → Actions → **Variables** タブ：

| 名前 | 値（Summary に表示されたもの） |
|---|---|
| `AWS_ROLE_ARN` | `arn:aws:iam::<ACCOUNT>:role/gha-slideforge-ecr-push` |
| `AWS_REGION` | `ap-northeast-1` |
| `ECR_REGISTRY` | `<ACCOUNT>.dkr.ecr.ap-northeast-1.amazonaws.com` |
| `ECR_REPOSITORY` | `slideforge/render` |

---

## 6. 片付け（ブートストラップ用権限を剥がす）

ブートストラップが済んだら、長期保管される admin キーを残さないために以下を実行。

### 6.1 AWS 側

IAM コンソール → Users → `slideforge-bootstrap`：

- **推奨**：ユーザーごと削除
- 最低限：アクセスキーを `Inactive` にするか削除

### 6.2 GitHub 側

Settings → Secrets and variables → Actions → Secrets：

- `BOOTSTRAP_AWS_ACCESS_KEY_ID` を削除
- `BOOTSTRAP_AWS_SECRET_ACCESS_KEY` を削除
- `BOOTSTRAP_AWS_REGION` は残しても可（機密でない）
- `ANTHROPIC_API_KEY` は残す（Nightly Eval 用に継続利用）

---

## 7. 初回パイプライン実行（本番起動）

main ブランチに変更を push：

- 空コミットで十分：`git commit --allow-empty -m "trigger first pipeline"` → `git push`
- GHA の `ci` ワークフローが走る
- main なので `render-image` ジョブが OIDC で AWS に認証 → ECR に image を push（tag `prod` も付与）
- ECR の push イベントで CodePipeline が自動起動
- Stg デプロイ → Smoke → Approval → Prod デプロイ

---

## 8. トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| bootstrap.yml が `confirm` エラー | confirm 欄が `BOOTSTRAP` と一致しない | 大文字で再入力 |
| `InvalidClientTokenId` | IAM キーが無効 / 削除済み | Secrets を更新 |
| `AccessDeniedException` (CDK bootstrap) | IAM ユーザーに AdministratorAccess がついていない | ポリシー付与を再確認 |
| `RepositoryAlreadyExistsException` | ECR リポジトリ重複（idempotent 検査漏れ） | ワークフロー側で既に `describe → skip` する構造。再実行で解消 |
| Pipeline Stack の初回デプロイで image が無くてフリーズ | 想定動作。image push で起動 | §7 の空コミット push で image を作る |
| `slideforge/anthropic` を再ローテしたい | ワークフローを再実行、または Secrets Manager で put-secret-value | 再実行コスト小 |
| 再ブートストラップ（やり直し）したい | 各ステップは冪等 | `bootstrap.yml` をもう一度 `BOOTSTRAP` で実行 |

---

## 9. （参考）ローカル手動ブートストラップ

GHA ワークフローを使わず、ローカル CLI で同じことを行いたい場合：

```bash
# 1. aws configure で admin プロファイルを用意
# 2. 以下を上から実行（ACCT はアカウント ID）

aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1

sed "s/AWS_ACCT/$ACCT/g" infra/bootstrap/gha-trust.json > /tmp/trust.json
sed "s/AWS_ACCT/$ACCT/g" infra/bootstrap/gha-permission.json > /tmp/perm.json
aws iam create-role --role-name gha-slideforge-ecr-push \
  --assume-role-policy-document file:///tmp/trust.json
aws iam put-role-policy --role-name gha-slideforge-ecr-push \
  --policy-name ecr-push --policy-document file:///tmp/perm.json

aws ecr create-repository --repository-name slideforge/render \
  --image-scanning-configuration scanOnPush=true

aws secretsmanager create-secret --name slideforge/anthropic \
  --secret-string "$ANTHROPIC_API_KEY"

cd infra && pip install -r requirements.txt && npm install -g aws-cdk
cdk bootstrap "aws://$ACCT/ap-northeast-1" \
  --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess
cdk deploy SlideForgePipelineStack --require-approval never
```

以降の流れは §5 以降と同じ。
