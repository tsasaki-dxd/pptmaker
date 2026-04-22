# Custom domain plan: `slideforge.dx-design.co.jp`

**ステータス**：未着手。Phase 1 のバグ修正と一次デプロイ完了後に実施。

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

## 進行順

| # | 作業 | 担当 | 所要 |
|---|---|---|---|
| 1 | CDK に ACM + CloudFront を追加して PR | Claude | 30 分 |
| 2 | PR レビュー + merge | user | — |
| 3 | Bootstrap 再実行（IAM Role のポリシーに acm/cloudfront 関連追加される場合） | user | 5 分 |
| 4 | main に push → Pipeline デプロイ | 自動 | 15 分 |
| 5 | CfnOutput から `AcmValidationCname*` を取得 | user | — |
| 6 | スターサーバーに検証用 CNAME 追加 | user | 5 分 |
| 7 | ACM 検証完了待ち（5〜30 分） | 自動 | 待機 |
| 8 | CloudFront 再デプロイ（証明書アタッチ） | 自動 / Pipeline | 10〜15 分 |
| 9 | スターサーバーに SPA 用 CNAME 追加 | user | 5 分 |
| 10 | `https://slideforge.dx-design.co.jp` 疎通確認 | user | — |

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
