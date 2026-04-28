# Custom domain plan: `slideforge.dx-design.co.jp`

**ステータス**：CDK 実装は merge 済み。`custom_domain` context フラグが
**未設定** の状態で main にいるので、AppStack は従来どおり public S3
website で動いている。スターサーバーに CNAME を 2 本追加して `cdk.json`
の `custom_domain` を埋めれば、次の merge で自動的に CloudFront へ切替。

## 目的
社内利用者が AWS の生成ドメイン（`d1abc....cloudfront.net` や
`abc.execute-api.ap-northeast-1.amazonaws.com`）ではなく、
**`https://slideforge.dx-design.co.jp`** でアクセスできるようにする。

## 前提
- 親ドメイン `dx-design.co.jp` は**スターサーバー**で取得・DNS 管理
- DNS の大移動（Route53 への委譲）はしない。**必要な CNAME 2 本だけ**
  スターサーバーに追加する方針
- AWS アカウント：`221789841733`（既存の SlideForge 本番アカウント）

## 最終アーキテクチャ

```
ブラウザ
  │ HTTPS
  ▼
https://slideforge.dx-design.co.jp
  │ Route: DNS CNAME (スターサーバ) → CloudFront
  ▼
CloudFront Distribution (ACM 証明書付き)
  ├─ /api/*  → API Gateway HTTP API (same-origin)
  └─ /*      → S3 Web Bucket (OAC 経由で private アクセス)
```

同一オリジンになるので **CORS の仕組みが不要**になる（FastAPI 側 CORS は
OPTIONS 対応だけに簡略化してよい）。Phase 1 の痛かった「S3 サイトが HTTP」
「API と Web でオリジン違いによる CORS」が同時に解消される。

## 必要な変更

### AWS 側 (CDK)
1. `acm.Certificate`（**リージョン us-east-1**、CloudFront 要件）
   - ドメイン名：`slideforge.dx-design.co.jp`
   - バリデーション：DNS（スターサーバーに CNAME 一本追加）
2. `cloudfront.Distribution`
   - Origin 1：S3 `web_bucket`（OAC で非公開化）
   - Origin 2：API Gateway HTTP API
   - CacheBehavior `/api/*`：Origin 2、キャッシュなし、全ヘッダ/クエリ/Cookie 透過
   - Default：Origin 1、キャッシュ有、404→`index.html` で SPA fallback
   - 証明書：上記の ACM
   - 代替ドメイン名：`slideforge.dx-design.co.jp`
3. `s3.Bucket` (`web_bucket`) を **private に戻す**
   - `public_read_access=False`
   - `block_public_access=BlockPublicAccess.BLOCK_ALL`
   - CloudFront の OAC からのみアクセス許可
4. `s3.Bucket` (`artifacts_bucket`) の CORS は現状維持（署名付き URL は
   変わらず、ブラウザから直接たたく）
5. `CfnOutput` を 3 つ追加
   - `DistributionDomainName` (例：`d1abc2345.cloudfront.net`)
   - `AcmValidationCnameName`
   - `AcmValidationCnameValue`

### アプリ側
6. `config.json` の `apiEndpoint` を `""`（空＝ same-origin、`/api/...` が
   そのまま効く）に変更
7. `FastAPI CORSMiddleware` の `allow_origins` を
   `["https://slideforge.dx-design.co.jp"]` に絞る（ワイルドカード廃止）

### オペレータ作業（ユーザ側）
8. ACM が出した検証用 CNAME をスターサーバーに登録（1 本目）
   - 例：`_abc123.slideforge` → `_xyz789.xxxxx.acm-validations.aws`
9. CloudFront のドメインへの CNAME をスターサーバーに登録（2 本目）
   - 例：`slideforge` → `d1abc2345.cloudfront.net`
10. DNS 伝播後、`https://slideforge.dx-design.co.jp` にアクセスして動作確認

## 進行順 (実装後の運用フロー)

| # | 作業 | 担当 | 所要 |
|---|---|---|---|
| 1 | CDK 実装 (CertStack + CloudFront をフラグ付きで追加) | Claude | done |
| 2 | フラグ OFF 状態で merge → 既存 S3 website に影響なくデプロイ | 自動 | done |
| 3 | `infra/cdk.json` の `context.custom_domain` を `"slideforge.dx-design.co.jp"` に変更してコミット | user | 5 分 |
| 4 | merge → Pipeline が `cdk deploy "*"` を実行<br>Cert-prod (us-east-1) が CREATE_IN_PROGRESS のまま停止 | 自動 → 待機 | 5 分 |
| 5 | AWS Console (us-east-1 → ACM) を開き、新しい cert の "CNAME name" / "CNAME value" を確認 | user | 1 分 |
| 6 | スターサーバーに検証用 CNAME 1 本追加 | user | 5 分 |
| 7 | ACM が検証を検出して Cert-prod が CREATE_COMPLETE | 自動 | 5〜30 分 |
| 8 | App-prod が CloudFront 含めデプロイ完了 | 自動 | 10〜15 分 |
| 9 | App-prod の `DistributionDomainName` 出力 (例 `d1abc...cloudfront.net`) を確認 | user | 1 分 |
| 10 | スターサーバーに SPA 用 CNAME (`slideforge` → 上記の CloudFront ドメイン) を追加 | user | 5 分 |
| 11 | `https://slideforge.dx-design.co.jp` 疎通確認 | user | — |

`config.json` の `apiEndpoint` は CloudFront があれば自動で `""`
(same-origin) に切替わる。スターサーバー側のスプリットホライゾン DNS は
不要 — 親ゾーンに CNAME 2 本だけ。

### 元に戻したい場合

`infra/cdk.json` の `context.custom_domain` を空文字または削除して
merge する。次のデプロイで AppStack は public S3 website に戻り、
Cert-prod は cloud assembly から消える (CDK が自動で CFN
delete-stack を発行)。スターサーバーに残る CNAME は手動で削除。

## 月額コスト差分
- ACM（AWS Certificate Manager）：**無料**
- CloudFront：低トラフィックで **$1〜2/月**（リクエスト + 転送量）
- Route53 ホストゾーン：**使わないので 0 円**
- 合計追加：**約 200〜300 JPY/月**

## 既存システムとの相互作用
- **HTTP S3 ホスティングの撤去**：CloudFront に寄せるので、S3 の
  static website hosting は無効化する（CloudFront が OAC で GetObject）
- **CORS の縮小**：same-origin 化で `allow_origins=["*"]` を
  `["https://slideforge.dx-design.co.jp"]` に変更
- **Cognito 設定**：Hosted UI を使っていないので callback URL の
  変更不要。ブラウザからの SRP は Cognito 公開エンドポイントを
  直接叩くだけなので引き続き動く

## やらないこと（今回のスコープ外）
- `dx-design.co.jp` 全体の DNS 移行（Route53 化）
- `www.slideforge....` への対応
- IP 許可リスト / WAF（Phase 2）
- 独自 TLS 1.3 only ポリシー（Phase 2）

## 参考リンク
- AWS: 「Adding an alternate domain name to your distribution」
- AWS: 「Requesting a public certificate in ACM」
- スターサーバー：ドメイン DNS 設定の CNAME 追加手順
