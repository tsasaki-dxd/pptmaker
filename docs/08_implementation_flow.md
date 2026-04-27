# 08. 実装フロー / Implementation Flow

## 目的とスコープ

本書は SlideForge の **実装層 (Phase 1)** におけるエンドツーエンドの処理フローを Mermaid 図で可視化し、
- API 受信 → DB → LLM → レンダリング → S3 保存 までの呼び出し順序
- 主要ジョブ (`BlueprintJob`, `Project` の render ステータス) の状態遷移
- エラーハンドリング/リトライの境界
を明示することを目的とする。

高レベルのコンポーネント責務は `SlideForge_概要設計書.md §4`、LLM 呼び出し設計は `01_prompt_engineering.md`、Phase 2 拡張は `07_phase2_design.md` を参照。本書は **コードに対する実装ビュー** を提供する。

参照対象コミット時点の主要ファイル:

| 役割 | ファイル |
| --- | --- |
| HTTP API ルータ | `app/api/routers/projects.py`, `app/api/routers/templates.py` |
| Blueprint 非同期ワーカ | `app/api/blueprint_worker.py` |
| Render Lambda ハンドラ | `app/render/handler.py` |
| ビジネスロジック | `app/api/services/{blueprint_builder,revision_handler,template_analyzer,template_registry,llm,queue,storage}.py` |
| DB ステータス更新 (psycopg2 直叩き) | `app/render/db_status.py` |
| ORM モデル | `app/api/models/db.py` |

---

## 1. システム全体俯瞰

主要コンポーネントとデータの流れ。SQS で API と非同期ワーカ (Blueprint / Render) が分離されている点が Phase 1 の前提。

```mermaid
flowchart LR
    subgraph Client["Client (Web)"]
        UI[Next.js UI]
    end

    subgraph API["API (FastAPI / ECS or Lambda)"]
        R_PROJ[routers/projects.py]
        R_TPL[routers/templates.py]
        R_IMG[routers/images.py]
    end

    subgraph Async["Async Workers"]
        BW[blueprint_worker.py]
        RH[render/handler.py]
    end

    subgraph LLM["Anthropic Claude"]
        L_BP[(Blueprint LLM)]
        L_REV[(Revision LLM)]
        L_DSG[(Layout Designer LLM)]
    end

    subgraph AWS["AWS Managed"]
        SQS_BP[[SQS: blueprint-jobs]]
        SQS_RD[[SQS: render-jobs]]
        S3_TPL[(S3: templates)]
        S3_OUT[(S3: outputs)]
        DB[(RDS PostgreSQL)]
    end

    UI -- presigned PUT --> S3_TPL
    UI <--> R_PROJ
    UI <--> R_TPL
    UI <--> R_IMG

    R_TPL --> DB
    R_TPL -- analyze on GET --> S3_TPL

    R_PROJ -- enqueue --> SQS_BP
    R_PROJ -- enqueue --> SQS_RD
    R_PROJ -- inline --> L_REV
    R_PROJ --> DB

    SQS_BP --> BW
    BW --> L_BP
    BW --> S3_TPL
    BW --> DB

    SQS_RD --> RH
    RH --> L_DSG
    RH --> S3_TPL
    RH --> S3_OUT
    RH --> DB
```

---

## 2. Blueprint 生成フロー (非同期)

`POST /api/projects/{project_id}/blueprint` をトリガとした骨格生成パイプライン。HTTP 応答は 202 で即返り、後段は SQS 経由でワーカが処理する。

```mermaid
sequenceDiagram
    autonumber
    participant UI as Web UI
    participant API as projects.py
    participant DB as RDS
    participant Q as SQS blueprint-jobs
    participant W as blueprint_worker.py
    participant TA as template_analyzer.py
    participant BB as blueprint_builder.py
    participant LLM as Claude (L1: Blueprint)

    UI->>API: POST /projects/{id}/blueprint<br/>{user_intent, required_sections}
    API->>DB: INSERT BlueprintJobRow<br/>status="pending"
    API->>Q: SendMessage {job_id, project_id,<br/>tenant_id, user_intent, ...}
    API-->>UI: 202 Accepted {job_id}

    Q-->>W: ReceiveMessage (at-least-once)
    W->>DB: SELECT BlueprintJobRow<br/>by job_id
    alt status != "pending"
        W-->>Q: ack (idempotent skip)
    else status == "pending"
        W->>DB: SELECT Project, TemplateProfile

        opt template.layouts 未解析
            W->>TA: analyze_template(s3_uri)
            TA->>DB: UPDATE template.layouts,<br/>template_slide_count, design_tokens
        end

        W->>BB: build_blueprint(user_intent,<br/>template_summary, ...)
        loop 最大 3 回 (MAX_RETRIES=2)
            BB->>LLM: messages.create (system+user)
            LLM-->>BB: JSON / max_tokens / 不正
            BB->>BB: extract_json + sanitize + validate
        end
        BB-->>W: parsed blueprint

        W->>W: _assign_template_mapping<br/>(slides ↔ template_slide_index)
        W->>DB: INSERT BlueprintRow<br/>(version=latest+1)
        W->>DB: UPDATE BlueprintJobRow<br/>status="complete", blueprint_id
        W-->>Q: ack
    end

    Note over UI,API: UI は GET /projects/{id}/blueprint/jobs/{job_id}<br/>でポーリング (Phase 1)
```

**主要参照点**: `projects.py:209-256` (受信), `blueprint_worker.py:60-167` (本体), `blueprint_builder.py:40-61` (LLM リトライ), `template_analyzer.py:158-199` (テンプレ解析)。

---

## 3. Render フロー (非同期)

`POST /api/projects/{project_id}/render` で `.pptx` / `.pdf` / `preview/*.jpg` を S3 に書き出す。Layout Designer LLM (L4) はコンテンツスライド毎に並列発火する。

```mermaid
sequenceDiagram
    autonumber
    participant UI as Web UI
    participant API as projects.py
    participant DB as RDS
    participant Q as SQS render-jobs
    participant H as render/handler.py
    participant LD as layout_designer (L4)
    participant ASM as pptx_assembler<br/>+ shapes / figures
    participant LO as LibreOffice
    participant S3 as S3 outputs

    UI->>API: POST /projects/{id}/render
    API->>DB: SELECT 最新 BlueprintRow,<br/>TemplateProfile
    API->>Q: SendMessage {job_id, blueprint,<br/>template_layouts, design_tokens, ...}
    API->>DB: UPDATE Project status="rendering"
    API-->>UI: 202 Accepted {job_id}

    Q-->>H: ReceiveMessage
    H->>S3: GET template.pptx → /tmp
    H->>ASM: safe_unpack + read_template_slides
    H->>ASM: derive_slides(blueprint ↔ template idx)

    par Layout Designer (最大 8 並列)
        H->>LD: design_layout(slide N)
        LD-->>H: design result
    and 他のスライド
        H->>LD: design_layout(slide M)
        LD-->>H: design result
    end

    loop 各 blueprint slide
        H->>ASM: render_content_slide<br/>(merge XML + designer + figures)
        alt 個別スライド失敗
            H->>H: skipped[] へ追加 (継続)
        end
    end

    H->>ASM: write_output_slides<br/>+ rewrite_presentation_xml
    H->>S3: PUT {prefix}/output.pptx

    opt PDF/Preview 生成
        H->>LO: pptx_to_pdf
        H->>LO: pdf_to_jpegs
        H->>S3: PUT {prefix}/output.pdf
        H->>S3: PUT {prefix}/preview/slide-NN.jpg
    end

    alt 全成功
        H->>DB: UPDATE Project status="complete"
    else PPTX 成功 / PDF or Preview 失敗
        H->>DB: UPDATE Project status="partial"
    else 例外
        H->>DB: UPDATE Project status="failed"
        H-->>Q: 例外再送 → リトライ → DLQ
    end
```

**主要参照点**: `projects.py:409-461` (受信), `handler.py:71-486` (本体), `db_status.py:23-104` (psycopg2 直接 UPDATE)。Project の status は ORM ではなく `db_status.py` 経由で更新される (Lambda のコールドスタート短縮目的)。

---

## 4. Revision フロー (同期 / インライン)

修正指示 (L2) は **HTTP リクエストスレッド上で同期実行** され、JSON Patch (RFC 6902) を生成・適用して新バージョンの `BlueprintRow` を作る。SQS は経由しない。

```mermaid
sequenceDiagram
    autonumber
    participant UI as Web UI
    participant API as projects.py
    participant DB as RDS
    participant RV as revision_handler.py
    participant LLM as Claude (L2: Revision)

    UI->>API: POST /projects/{id}/revise<br/>{instruction}
    API->>DB: SELECT 最新 BlueprintRow
    API->>RV: apply_instruction(blueprint, instruction)
    RV->>LLM: messages.create<br/>(JSON Patch 期待)
    LLM-->>RV: [{op, path, value}, ...]
    RV->>RV: _check_patch_safety<br/>(op/path ホワイトリスト)
    alt 違反
        RV-->>API: 例外
        API-->>UI: 4xx
    else OK
        RV->>RV: jsonpatch.apply_patch
        RV-->>API: new_blueprint
        API->>DB: INSERT BlueprintRow<br/>(version=current+1)
        API->>DB: INSERT RevisionRow<br/>(patch, instruction, applied=1)
        API-->>UI: 200 {blueprint_id, version}
    end
```

**注意**: LLM 呼び出しが HTTP 応答時間に直結する。長文指示は API Gateway / ALB のタイムアウト (典型 30s) を超えるリスクがある。Phase 2 では非同期化候補。

**主要参照点**: `projects.py:343-406`, `revision_handler.py:23-50`。

---

## 5. テンプレート登録 / 解析フロー

登録は presigned PUT で先にレコードと URL を作成し、解析は **GET 時遅延実行** または Blueprint ワーカ起動時に実行される (どちらが先でも同じ結果)。

```mermaid
sequenceDiagram
    autonumber
    participant UI as Web UI
    participant API as templates.py
    participant DB as RDS
    participant S3 as S3 templates
    participant TA as template_analyzer.py
    participant TR as template_registry.py
    participant SE as slot_extractor.py

    UI->>API: POST /templates {name}
    API->>DB: INSERT TemplateProfileRow<br/>(layouts=[], slide_count=0)
    API->>S3: presigned PUT URL 発行
    API-->>UI: {template_id, upload_url}

    UI->>S3: PUT template.pptx (multipart)

    UI->>API: GET /templates/{id}?refresh=0
    alt 未解析 or refresh=1
        API->>TA: analyze_template(s3_uri)
        TA->>S3: GET template.pptx
        TA->>TR: classify_layouts<br/>(cover/toc/section/content/...)
        loop 各スライド
            TA->>SE: extract_slots → [{id,kind,role,rect}]
        end
        TA-->>API: {slide_count, layouts, design_tokens}
        API->>DB: UPDATE TemplateProfile.layouts,<br/>template_slide_count, design_tokens
    end
    API-->>UI: TemplateProfile JSON
```

**主要参照点**: `templates.py:49-109`, `template_analyzer.py:158-199`, `template_registry.py:43-54`, `render/slot_extractor.py`。

---

## 6. ジョブ状態遷移図

### 6.1 BlueprintJob

`BlueprintJobRow.status` は単純な3状態。SQS 再配信は `pending` 以外なら no-op で吸収する (`blueprint_worker.py:68-71`)。

```mermaid
stateDiagram-v2
    [*] --> pending: API: INSERT (projects.py)
    pending --> complete: worker 成功<br/>(blueprint_id 紐付け)
    pending --> failed: worker validate/build 失敗<br/>(error_message セット)
    complete --> [*]
    failed --> [*]

    pending --> pending: SQS 再配信<br/>(idempotent skip)
```

| 終端状態 | トリガ | 残置データ |
| --- | --- | --- |
| `complete` | `BlueprintBuildError` 以外で正常終了 | `blueprint_id` が新規 BlueprintRow を指す |
| `failed` | `BlueprintBuildError` / project 消失 / template 消失 | `error_message` (≤2000 文字) |

**transient 例外** (DB 接続断, Secrets Manager, Anthropic transport) は再 raise され、SQS が再配信 → 規定回数で DLQ へ。アプリ側はリトライ回数を持たない。

### 6.2 Project (render ステータス)

`ProjectRow.status` は draft 状態を含めた5状態。`render` 実行中以降は `db_status.py` から psycopg2 直 UPDATE される。

```mermaid
stateDiagram-v2
    [*] --> draft: POST /projects 直後
    draft --> rendering: POST /render
    rendering --> complete: PPTX+PDF+Preview 全成功
    rendering --> partial: PPTX 成功<br/>but PDF/Preview 失敗
    rendering --> failed: 例外で中断<br/>(SQS 再配信対象)
    complete --> rendering: 再 render
    partial --> rendering: 再 render
    failed --> rendering: 再 render
    complete --> [*]
```

| 状態 | 観測ポイント | UI 取り扱い |
| --- | --- | --- |
| `draft` | ブループリント未生成も含む | render ボタン無効 |
| `rendering` | SQS 投入後 〜 Lambda 完了前 | スピナー / ポーリング |
| `complete` | `output.pptx`, `output.pdf`, `preview/*.jpg` 揃う | DL 全種類有効 |
| `partial` | `output.pptx` のみ揃う (PDF/Preview 失敗) | PPTX のみ DL、警告表示 |
| `failed` | Lambda 例外 → DB 更新 | 再 render を促す |

### 6.3 TemplateProfile

明示的 status カラムは無く、`template_slide_count == 0` を「未解析」のセンチネルとして扱う。`layouts` の有無で再解析を判定する (`blueprint_worker.py:96`)。

---

## 7. エラーハンドリング / リトライ境界

| シナリオ | コード位置 | 方針 |
| --- | --- | --- |
| Blueprint LLM 出力検証失敗 | `blueprint_builder.py:40-61` | アプリ内で最大 3 回試行 (MAX_RETRIES=2)、失敗時 `BlueprintBuildError` |
| LLM `stop_reason==max_tokens` | `blueprint_builder.py:53-57` | リトライしても改善しないため即座に終端エラー |
| Blueprint ワーカ中の transient 例外 | `blueprint_worker.py:154-159` | rollback して raise → SQS が再配信 → 既定回数超で DLQ |
| Blueprint ワーカ idempotency | `blueprint_worker.py:68-71` | `status != "pending"` なら処理スキップ (at-least-once 対策) |
| Render 個別スライド失敗 | `handler.py:434-444` | 当該スライドはテンプレ XML をそのまま採用、`skipped[]` に記録、処理継続 |
| Render PDF/Preview 失敗 | `handler.py:481-486` | 例外を握り潰し `partial` でクローズ、PPTX は配信 |
| Render 例外 (本体不可) | `handler.py:99-106` | DB を `failed` にして例外再送 → SQS リトライ → DLQ |
| Revision Patch 安全性 | `revision_handler.py:45` | op/path のホワイトリスト違反は適用前に拒否 |
| SQS 可視性タイムアウト・DLQ 設定 | `infra/stacks/app_stack.py` | アプリコードでなく CDK 定義側で持つ |

---

## 8. データ受け渡しサマリ

| ペイロード | 主なキー | 概算サイズ |
| --- | --- | --- |
| Blueprint job (SQS) | `job_id, project_id, tenant_id, user_intent, required_sections, aux_context` | ~1KB |
| Render job (SQS) | `job_id, tenant_id, project_id, template_s3, blueprint, template_layouts, design_tokens, out_prefix` | 5–50 KB |
| Blueprint オブジェクト (DB) | `title, slides[].{index, layout, figure_type, content.slots, template_slide_index, ...}` | 1–50 KB |
| Revision Patch (DB) | RFC 6902 配列 `[{op, path, value}, ...]` | ~1 KB / リビジョン |

SQS 1メッセージ上限 (256KB) に対して Render ペイロードは余裕があるが、design_tokens に画像 base64 等を入れると逼迫するため文字列配色トークンに限定している (`07_phase2_design.md §3` 参照)。

---

## 9. 関連ドキュメント

- `SlideForge_概要設計書.md`: 高レベルアーキテクチャ・コンポーネント責務
- `01_prompt_engineering.md`: LLM 呼び出し L1〜L6 の入出力契約
- `03_ops_and_testing.md`: CI/CD・監視・SLO
- `04_template_and_plugin.md`: テンプレ解析と図表プラグイン IF
- `07_phase2_design.md`: Slot/レンダリングの将来拡張
- `visual_qa_workflow.md`: PPTX→PNG 経由のビジュアル QA フロー
