# SlideForge 初回ブートストラップ Runbook

**対象読者**：SlideForge の AWS 環境を初めてセットアップする運用担当者
**前提**：AWS Organization / アカウント（infra / dev / stg / prod）は作成済み、管理者権限を保有
**所要時間**：2〜4 時間（アカウント作成完了後）
**参照**：`docs/03_ops_and_testing.md` §8, §15 / `docs/05_security_compliance.md`

---

## 0. この Runbook の使い方

- 各ステップは**冪等**になるよう書かれている（再実行しても壊れない）
- 失敗時は該当セクションの **Rollback** を参照
- 完了したら末尾の **Verification** を全て通過させる
- 2 回目以降の環境追加（新リージョン等）は §7 を参照

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
aws configure sso --profile slideforge-infra
aws configure sso --profile slideforge-dev
aws configure sso --profile slideforge-stg
aws configure sso --profile slideforge-prod

# 動作確認
for p in infra dev stg prod; do
  aws sts get-caller-identity --profile slideforge-$p
done
```

### 1.3 環境変数

```bash
export INFRA_ACCT=111111111111
export DEV_ACCT=222222222222
export STG_ACCT=333333333333
export PROD_ACCT=444444444444
export AWS_REGION=ap-northeast-1
export GH_ORG=tsasaki-dxd
export GH_REPO=pptmaker
```

---

## 2. CDK ブートストラップ（各アカウント 1 回）

Pipeline をホストする infra アカウントと、デプロイ先の 3 アカウントに CDK の土台を配置する。

```bash
# infra アカウント（Pipeline の本体が住む）
npx cdk bootstrap aws://$INFRA_ACCT/$AWS_REGION \
  --profile slideforge-infra \
  --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess

# dev / stg / prod（Pipeline からデプロイされる側）
for acct in $DEV_ACCT $STG_ACCT $PROD_ACCT; do
  profile=$(case $acct in
    $DEV_ACCT) echo slideforge-dev;;
    $STG_ACCT) echo slideforge-stg;;
    $PROD_ACCT) echo slideforge-prod;;
  esac)
  npx cdk bootstrap aws://$acct/$AWS_REGION \
    --profile $profile \
    --trust $INFRA_ACCT \
    --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess
done
```

`--trust $INFRA_ACCT` で、infra アカウントの Pipeline がデプロイ先アカウントにリソースを作成できるようになる。

**Rollback**：`npx cdk bootstrap --force` で作り直し、または CloudFormation コンソールで `CDKToolkit` スタックを削除。

---

## 3. GitHub Actions → AWS の OIDC 設定（infra アカウント）

### 3.1 IAM OIDC Provider 作成

```bash
aws iam create-open-id-connect-provider \
  --profile slideforge-infra \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

thumbprint は GitHub 側の証明書更新で変わりうるので、年次でレビュー。

### 3.2 GHA 用 IAM Role 作成

`infra/bootstrap/gha-role.json`（Trust Policy）:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::INFRA_ACCT:oidc-provider/token.actions.githubusercontent.com"
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

Permission Policy（ECR push のみ）:

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

作成コマンド（`INFRA_ACCT` を実値に置換してから）:

```bash
sed -i "s/INFRA_ACCT/$INFRA_ACCT/g" infra/bootstrap/gha-role.json

aws iam create-role \
  --profile slideforge-infra \
  --role-name gha-slideforge-ecr-push \
  --assume-role-policy-document file://infra/bootstrap/gha-role.json

aws iam put-role-policy \
  --profile slideforge-infra \
  --role-name gha-slideforge-ecr-push \
  --policy-name ecr-push \
  --policy-document file://infra/bootstrap/gha-permission.json
```

---

## 4. ECR リポジトリ作成（infra アカウント）

`prod` タグの push を CodePipeline が監視するので、ECR は infra アカウントに置く。

```bash
aws ecr create-repository \
  --profile slideforge-infra \
  --repository-name slideforge/api \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=KMS
```

デプロイ先アカウントから pull できるよう、Repository Policy を設定：

```bash
cat > /tmp/ecr-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "AllowCrossAccountPull",
    "Effect": "Allow",
    "Principal": {
      "AWS": [
        "arn:aws:iam::$DEV_ACCT:root",
        "arn:aws:iam::$STG_ACCT:root",
        "arn:aws:iam::$PROD_ACCT:root"
      ]
    },
    "Action": [
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:BatchCheckLayerAvailability"
    ]
  }]
}
EOF

aws ecr set-repository-policy \
  --profile slideforge-infra \
  --repository-name slideforge/api \
  --policy-text file:///tmp/ecr-policy.json
```

---

## 5. GitHub リポジトリ設定

### 5.1 Variables を登録

GitHub → Settings → Secrets and variables → Actions → **Variables** タブ（Secrets ではない）：

| Name | Value |
|---|---|
| `AWS_ROLE_ARN` | `arn:aws:iam::<INFRA_ACCT>:role/gha-slideforge-ecr-push` |
| `AWS_REGION` | `ap-northeast-1` |
| `ECR_REGISTRY` | `<INFRA_ACCT>.dkr.ecr.ap-northeast-1.amazonaws.com` |
| `ECR_REPOSITORY` | `slideforge/api` |

### 5.2 Environments（承認用）

GitHub → Settings → Environments で `staging` と `production` を作成し、production には Required reviewers を 2 名以上設定（本番昇格時の明示承認）。CodePipeline 承認と二重に掛かるのを許容するかは運用ルールで決める。

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
npx cdk synth --profile slideforge-infra
```

出力 CloudFormation に不審なリソースが無いか確認。

### 6.3 デプロイ

```bash
npx cdk deploy SlideForgePipelineStack \
  --profile slideforge-infra \
  --require-approval broadening
```

**所要：15〜25 分**。完了すると CodePipeline / ECR / 必要な IAM Role / S3 Artifact バケット / KMS が作成される。

### 6.4 初回パイプライン実行

この時点ではまだ ECR に image が無いので、Pipeline は起動しない。以下のいずれかで初回を走らせる：

**A. GHA から通常フローで**（推奨）
- main に空コミット or 些細な変更を merge
- GHA が ECR に `prod` タグで push
- 自動的に Pipeline が起動

**B. 手動 image push**（デバッグ用）
```bash
aws ecr get-login-password --profile slideforge-infra | \
  docker login --username AWS --password-stdin $INFRA_ACCT.dkr.ecr.$AWS_REGION.amazonaws.com
docker pull public.ecr.aws/docker/library/hello-world:latest
docker tag hello-world:latest $INFRA_ACCT.dkr.ecr.$AWS_REGION.amazonaws.com/slideforge/api:prod
docker push $INFRA_ACCT.dkr.ecr.$AWS_REGION.amazonaws.com/slideforge/api:prod
```

---

## 7. 環境追加（2 回目以降・参考）

新しい環境（例：`preprod`）を足す場合：

1. AWS アカウント作成、`cdk bootstrap --trust $INFRA_ACCT` 実行
2. `infra/stages/app_stage.py` に PreprodStage を追加
3. `infra/stacks/pipeline_stack.py` で Pipeline に `add_stage` で挟み込む
4. PR を main に merge → 自己更新でステージが増える

---

## 8. Verification（完了チェック）

以下が全て Yes になったらブートストラップ完了。

- [ ] `aws sts get-caller-identity` が 4 アカウント全てで成功
- [ ] infra / dev / stg / prod アカウントに `CDKToolkit` スタックが存在
- [ ] IAM に `gha-slideforge-ecr-push` Role が存在、Trust が repo 限定
- [ ] ECR リポジトリ `slideforge/api` が存在、scanOnPush 有効
- [ ] GitHub Variables に 4 つのキーが登録
- [ ] `SlideForgePipelineStack` が infra アカウントで CREATE_COMPLETE
- [ ] 初回 image push で Pipeline が起動した
- [ ] Dev → Stg → Prod まで展開完了
- [ ] CodeDeploy Blue/Green ログに `Succeeded`
- [ ] CloudTrail に `AssumeRoleWithWebIdentity` イベントが記録されている
- [ ] ECR に `sha-<commit>` と `prod` のタグが両方存在

---

## 9. トラブルシューティング

| 症状 | 原因候補 | 対処 |
|---|---|---|
| GHA で `Error: Could not assume role` | Trust Policy の `sub` が不一致、リポ名タイポ | sub 条件を `repo:tsasaki-dxd/pptmaker:*` で一旦広げて検証、確定後に絞る |
| `cdk deploy` で `Need to perform AWS calls for account ... but no credentials` | CLI プロファイルが有効でない | `aws sso login --profile slideforge-infra` 再実行 |
| Pipeline が image push で起動しない | EventBridge Rule 未作成、タグ不一致 | EventBridge コンソールで該当 Rule が Enabled か、タグが `prod` か確認 |
| CodeDeploy が dev で Permission denied | ECR Repository Policy に dev アカウント未追加 | §4 の Policy 再適用 |
| 自己更新が暴走（望まない変更） | `infra/` の誤変更 | Pipeline コンソールで最新実行を Stop → main で revert PR |

---

## 10. 権限剥がし（ブートストラップ完了後）

作業中に使った **管理者権限は剥がす**。

- 作業担当者の Identity Center グループから `AdministratorAccess` を外す
- 通常時は `PowerUserAccess` + 必要に応じた Approve Role に絞る
- `cdk bootstrap` に使った `--cloudformation-execution-policies AdministratorAccess` は、プロジェクト成熟後に最小権限へ絞る（`cdk bootstrap --custom-permissions-boundary` で）
