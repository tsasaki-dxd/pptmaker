# SlideForge 初回ブートストラップ Runbook（Phase 1）

**対象読者**：SlideForge の AWS 環境を初めてセットアップする運用担当者
**前提**：AWS アカウント 1 つ、管理者権限を保有
**所要時間**：1〜2 時間
**参照**：`docs/03_ops_and_testing.md` §8, §15 / `docs/SlideForge_概要設計書.md` §3

---

## 0. この Runbook の使い方

- Phase 1 は **単一 AWS アカウント** で運用（Dev / Stg / Prod は同一アカウント内の Stack 分離）
- 各ステップは**冪等**（再実行しても壊れない）
- 完了したら末尾の **Verification** を全て通過させる
- Phase 2 でマルチアカウント化する際の手順は §7 を参照

---

## 1. 前提ツールの準備（ローカル）

### 1.1 ツールインストール

| ツール | 要件 | 確認コマンド |
|---|---|---|
| AWS CLI | v2.15 以上 | `aws --version` |
| Node.js | v20 以上（CDK 実行用） | `node --version` |
| AWS CDK | v2.140 以上 | `npx cdk --version` |
| Python | 3.12 | `python3 --version` |
| Docker | 動作中 | `docker info` |
| git | 2.40 以上 | `git --version` |

### 1.2 AWS SSO / プロファイル設定

```bash
aws configure sso --profile slideforge

# 動作確認
aws sts get-caller-identity --profile slideforge
```

### 1.3 環境変数

```bash
export AWS_ACCT=111111111111       # 使用する AWS アカウント ID
export AWS_REGION=ap-northeast-1
export AWS_PROFILE=slideforge
export GH_ORG=tsasaki-dxd
export GH_REPO=pptmaker
```

---

## 2. CDK ブートストラップ（1 回のみ）

```bash
npx cdk bootstrap aws://$AWS_ACCT/$AWS_REGION \
  --profile $AWS_PROFILE \
  --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess
```

これで `CDKToolkit` スタックが作成され、CDK が Artifact 保管用の S3 / ECR を準備する。

**Phase 2 移行時の追加作業**：Dev / Stg / Prod の独立アカウントでそれぞれ `cdk bootstrap --trust $INFRA_ACCT` を実行（§7 参照）。

---

## 3. GitHub Actions → AWS の OIDC 設定

### 3.1 IAM OIDC Provider 作成

```bash
aws iam create-open-id-connect-provider \
  --profile $AWS_PROFILE \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### 3.2 GHA 用 IAM Role 作成

`infra/bootstrap/gha-trust.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::AWS_ACCT:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
      },
      "StringLike": {
        "token.actions.githubusercontent.com:sub": "repo:tsasaki-dxd/pptmaker:*"
      }
    }
  }]
}
```

`infra/bootstrap/gha-permission.json`（ECR push のみ）:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "ecr:GetAuthorizationToken",
      "ecr:BatchCheckLayerAvailability",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload"
    ],
    "Resource": "*"
  }]
}
```

作成コマンド：

```bash
sed -i "s/AWS_ACCT/$AWS_ACCT/g" infra/bootstrap/gha-trust.json

aws iam create-role \
  --profile $AWS_PROFILE \
  --role-name gha-slideforge-ecr-push \
  --assume-role-policy-document file://infra/bootstrap/gha-trust.json

aws iam put-role-policy \
  --profile $AWS_PROFILE \
  --role-name gha-slideforge-ecr-push \
  --policy-name ecr-push \
  --policy-document file://infra/bootstrap/gha-permission.json
```

---

## 4. ECR リポジトリ作成

Render Lambda 用の Container Image を格納。

```bash
aws ecr create-repository \
  --profile $AWS_PROFILE \
  --repository-name slideforge/render \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=KMS
```

Phase 1 は単一アカウントなので、クロスアカウント pull 用の Repository Policy は不要（Phase 2 で追加）。

---

## 5. GitHub リポジトリ設定

### 5.1 Variables を登録

GitHub → Settings → Secrets and variables → Actions → **Variables** タブ：

| Name | Value |
|---|---|
| `AWS_ROLE_ARN` | `arn:aws:iam::<AWS_ACCT>:role/gha-slideforge-ecr-push` |
| `AWS_REGION` | `ap-northeast-1` |
| `ECR_REGISTRY` | `<AWS_ACCT>.dkr.ecr.ap-northeast-1.amazonaws.com` |
| `ECR_REPOSITORY` | `slideforge/render` |

**Secrets は登録しない**（静的 AWS キーは OIDC で不要）。

### 5.2 Environments（承認用）

`production` Environment を作成し、Required reviewers を 2 名以上設定（CodePipeline 承認と重ね掛けする場合のみ）。Phase 1 は CodePipeline の承認ステージだけでも運用可能。

### 5.3 ブランチ保護

main ブランチに：
- PR 必須、1 人以上の approve
- Required status checks: lint / unit / integration / visual-regression
- Squash merge 推奨

---

## 6. Pipeline Stack のデプロイ（1 回のみ手動）

### 6.1 infra/ セットアップ

```bash
cd infra
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 6.2 synth 確認

```bash
npx cdk synth --profile $AWS_PROFILE
```

### 6.3 デプロイ

```bash
npx cdk deploy SlideForgePipelineStack \
  --profile $AWS_PROFILE \
  --require-approval broadening
```

**所要：10〜15 分**。CodePipeline、CodeBuild、CodeDeploy、必要な IAM Role、S3 Artifact バケット、KMS が作成される。

### 6.4 初回パイプライン実行

ECR にまだ image が無いので、以下のいずれかで初回起動：

**A. GHA から通常フローで**（推奨）
- main に空コミット → GHA が Render Image を ECR の `prod` タグで push → Pipeline 自動起動

**B. 手動 image push**（デバッグ用）
```bash
aws ecr get-login-password --profile $AWS_PROFILE | \
  docker login --username AWS --password-stdin $AWS_ACCT.dkr.ecr.$AWS_REGION.amazonaws.com
docker pull public.ecr.aws/docker/library/hello-world:latest
docker tag hello-world:latest $AWS_ACCT.dkr.ecr.$AWS_REGION.amazonaws.com/slideforge/render:prod
docker push $AWS_ACCT.dkr.ecr.$AWS_REGION.amazonaws.com/slideforge/render:prod
```

---

## 7. Phase 2 でマルチアカウント化する際の追加手順（参考）

Phase 1 の単一アカウントから Phase 2 で分離する場合：

1. AWS Organization で Dev / Stg / Prod アカウントを追加作成
2. 各アカウントで `cdk bootstrap aws://<acct>/ap-northeast-1 --trust $INFRA_ACCT`
3. ECR の Repository Policy に `Dev/Stg/Prod` アカウントの pull 権限を追加
4. `infra/stages/app_stage.py` の `env` 指定を各アカウント ID に切替
5. CodePipeline を CrossAccount 構成に更新（`cross_account_keys=True`）
6. データ移行（RDS → Aurora）を別途計画

---

## 8. Verification（完了チェック）

- [ ] `aws sts get-caller-identity --profile slideforge` が成功
- [ ] `CDKToolkit` スタックが存在
- [ ] IAM に `gha-slideforge-ecr-push` Role が存在、Trust が repo 限定
- [ ] ECR リポジトリ `slideforge/render` が存在、scanOnPush 有効
- [ ] GitHub Variables に 4 つのキーが登録
- [ ] `SlideForgePipelineStack` が CREATE_COMPLETE
- [ ] 初回 image push で Pipeline が起動した
- [ ] Stg → Prod まで展開完了
- [ ] CodeDeploy の Lambda alias 切替ログに `Succeeded`
- [ ] CloudTrail に `AssumeRoleWithWebIdentity` イベントが記録されている

---

## 9. トラブルシューティング

| 症状 | 原因候補 | 対処 |
|---|---|---|
| GHA で `Error: Could not assume role` | Trust Policy の `sub` が不一致、リポ名タイポ | `sub` 条件を `repo:tsasaki-dxd/pptmaker:*` で一旦広げて検証、確定後に絞る |
| `cdk deploy` で `no credentials` | CLI プロファイルが未ログイン | `aws sso login --profile slideforge` 再実行 |
| Pipeline が image push で起動しない | EventBridge Rule 未作成、タグ不一致 | EventBridge コンソールで Rule が Enabled か、タグが `prod` か確認 |
| Lambda デプロイで Permission denied | Lambda 実行ロールの IAM 不足 | CDK の `grant_*` 記述を確認 |
| 自己更新が暴走（望まない変更） | `infra/` の誤変更 | Pipeline コンソールで Stop → main で revert PR |

---

## 10. 権限剥がし（ブートストラップ完了後）

- 作業担当者の Identity Center グループから `AdministratorAccess` を外す
- 通常時は `PowerUserAccess` + 必要に応じた Approve Role に絞る
- `cdk bootstrap --custom-permissions-boundary` で最小権限化はプロジェクト成熟後に実施
