"""Catalog of rendering samples shown in the /samples gallery.

Each entry produces a single PNG under
``app/web/public/samples/<figure_type>/<id>.png`` plus a manifest entry
read by the web UI. The shapes in ``spec`` are EMU-positioned inside
the DXDesignSystem template's content body box:

    body_rect = (x=365_760, y=1_737_360, w=8_412_480, h=2_834_640)

Samples should stay inside that rect — sample renders that overflow
will visibly clip into the template's footer or eyebrow.

To add a new sample: append a Sample(...) below. Then run
``python -m scripts.generate_samples`` to (re)generate PNGs and the
manifest.
"""

from __future__ import annotations

from dataclasses import dataclass

from render.layout_spec import (
    BarChartShape,
    BarItem,
    BarSeries,
    CellSpec,
    ColumnSpec,
    LayoutSpec,
    LineChartShape,
    LineSeries,
    PieChartShape,
    PieSlice,
    PillShape,
    RectShape,
    TableShape,
    TextParagraphSpec,
    TextRunSpec,
    TextShape,
)


@dataclass(frozen=True)
class Sample:
    """One renderable example. ``figure_type`` groups the gallery
    filter; ``prompt`` is the natural-language brief that would
    plausibly elicit this layout from the designer LLM.

    Two rendering modes:

    * ``spec`` set → LayoutSpec (designer-style primitive composition)
      goes through emit_layout_spec.
    * ``figure_content`` set → dispatched to the figure_renderer
      registered under ``figure_type`` (the existing deterministic
      preset path).
    """

    id: str
    figure_type: str
    title: str
    prompt: str
    spec: LayoutSpec | None = None
    figure_content: dict | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        # Exactly one of (spec, figure_content) must be set.
        if (self.spec is None) == (self.figure_content is None):
            raise ValueError(
                f"Sample {self.id!r}: set exactly one of `spec` or `figure_content`"
            )


# Body container — every shape's x/y/w/h must fit inside this.
BODY_X = 365_760
BODY_Y = 1_737_360
BODY_W = 8_412_480
BODY_H = 2_834_640


def _full_body_rect() -> tuple[int, int, int, int]:
    return BODY_X, BODY_Y, BODY_W, BODY_H


# ---- Table ---------------------------------------------------------------


_TABLE_BASIC = TableShape(
    name="basic_table",
    x=BODY_X + 200_000,
    y=BODY_Y + 200_000,
    w=BODY_W - 400_000,
    h=BODY_H - 400_000,
    rows=[
        ["項目", "Q1", "Q2", "Q3", "Q4"],
        ["売上", "120", "145", "168", "201"],
        ["利益", "12", "18", "24", "32"],
        ["利益率", "10.0%", "12.4%", "14.3%", "15.9%"],
    ],
    columns=[
        ColumnSpec(weight=2, align="l"),
        ColumnSpec(weight=1, align="r"),
        ColumnSpec(weight=1, align="r"),
        ColumnSpec(weight=1, align="r"),
        ColumnSpec(weight=1, align="r"),
    ],
    header=True,
    alt_row_bg=True,
)

_TABLE_COL_SPAN = TableShape(
    name="span_table",
    x=BODY_X + 400_000,
    y=BODY_Y + 200_000,
    w=BODY_W - 800_000,
    h=BODY_H - 400_000,
    rows=[
        [CellSpec(text="2024 年度通期業績", col_span=4, align="ctr"), "", "", ""],
        ["事業セグメント", "売上", "利益", "成長率"],
        ["コア事業", "1,200", CellSpec(text="180", bold=True), "+8%"],
        ["新規事業", "320", CellSpec(text="-15", text_color="amber", bold=True), "+45%"],
        ["保守事業", "450", "62", "-2%"],
    ],
    header=True,
    alt_row_bg=False,
)

_TABLE_ROW_SPAN = TableShape(
    name="rowspan_table",
    x=BODY_X + 600_000,
    y=BODY_Y + 200_000,
    w=BODY_W - 1_200_000,
    h=BODY_H - 400_000,
    rows=[
        ["カテゴリ", "施策", "効果"],
        [
            CellSpec(text="顧客獲得", row_span=2, align="ctr", bold=True),
            "オンボーディング改善",
            "+12% CVR",
        ],
        ["", "リファラル制度導入", "+8% MAU"],
        [
            CellSpec(text="顧客維持", row_span=2, align="ctr", bold=True),
            "サポート即応化",
            "-15% 解約率",
        ],
        ["", "パーソナライゼーション", "+18% NPS"],
    ],
    header=True,
    alt_row_bg=True,
)


# ---- Bar chart -----------------------------------------------------------


_BAR_SIMPLE_V = BarChartShape(
    name="quarterly_revenue",
    x=BODY_X + 600_000,
    y=BODY_Y + 100_000,
    w=BODY_W - 1_200_000,
    h=BODY_H - 200_000,
    items=[
        BarItem(label="Q1", value=120),
        BarItem(label="Q2", value=145),
        BarItem(label="Q3", value=168),
        BarItem(label="Q4", value=201),
    ],
    orientation="v",
    show_values=True,
)

_BAR_SIMPLE_H = BarChartShape(
    name="region_share",
    x=BODY_X + 600_000,
    y=BODY_Y + 100_000,
    w=BODY_W - 1_200_000,
    h=BODY_H - 200_000,
    items=[
        BarItem(label="関東", value=58),
        BarItem(label="関西", value=24),
        BarItem(label="中部", value=12),
        BarItem(label="九州", value=6),
    ],
    orientation="h",
    show_values=True,
    value_format="{:g}%",
)

_BAR_GROUPED_V = BarChartShape(
    name="yoy_grouped",
    x=BODY_X + 400_000,
    y=BODY_Y + 100_000,
    w=BODY_W - 800_000,
    h=BODY_H - 200_000,
    series=[
        BarSeries(name="2023", values=[80, 95, 110, 130]),
        BarSeries(name="2024", values=[120, 145, 168, 201]),
    ],
    categories=["Q1", "Q2", "Q3", "Q4"],
    mode="grouped",
    orientation="v",
    show_values=True,
)

_BAR_STACKED_V = BarChartShape(
    name="channel_stacked",
    x=BODY_X + 400_000,
    y=BODY_Y + 100_000,
    w=BODY_W - 800_000,
    h=BODY_H - 200_000,
    series=[
        BarSeries(name="自社EC", values=[40, 55, 70, 90]),
        BarSeries(name="モール", values=[60, 65, 70, 80]),
        BarSeries(name="店舗", values=[20, 25, 28, 31]),
    ],
    categories=["Q1", "Q2", "Q3", "Q4"],
    mode="stacked",
    orientation="v",
    show_values=False,
)

_BAR_STACKED100_V = BarChartShape(
    name="cost_mix_pct",
    x=BODY_X + 400_000,
    y=BODY_Y + 100_000,
    w=BODY_W - 800_000,
    h=BODY_H - 200_000,
    series=[
        BarSeries(name="人件費", values=[55, 50, 45, 40]),
        BarSeries(name="広告費", values=[20, 25, 30, 35]),
        BarSeries(name="その他", values=[25, 25, 25, 25]),
    ],
    categories=["FY21", "FY22", "FY23", "FY24"],
    mode="stacked100",
    orientation="v",
    show_values=False,
)


# ---- Line chart ----------------------------------------------------------


_LINE_SINGLE = LineChartShape(
    name="mau_trend",
    x=BODY_X + 400_000,
    y=BODY_Y + 100_000,
    w=BODY_W - 800_000,
    h=BODY_H - 300_000,
    series=[LineSeries(name="MAU", values=[10, 14, 18, 26, 38, 52])],
    x_labels=["1月", "2月", "3月", "4月", "5月", "6月"],
    show_markers=True,
)

_LINE_MULTI = LineChartShape(
    name="kpi_trend",
    x=BODY_X + 400_000,
    y=BODY_Y + 100_000,
    w=BODY_W - 800_000,
    h=BODY_H - 300_000,
    series=[
        LineSeries(name="売上", values=[100, 110, 125, 145, 168, 201], color="primary"),
        LineSeries(name="原価", values=[60, 62, 70, 80, 90, 105], color="muted"),
        LineSeries(name="粗利", values=[40, 48, 55, 65, 78, 96], color="amber"),
    ],
    x_labels=["1月", "2月", "3月", "4月", "5月", "6月"],
    show_markers=True,
)


# ---- Pie chart -----------------------------------------------------------


_PIE_BASIC = PieChartShape(
    name="market_share",
    x=BODY_X + 1_200_000,
    y=BODY_Y + 200_000,
    w=BODY_H - 400_000,  # square — height-bound
    h=BODY_H - 400_000,
    slices=[
        PieSlice(label="Aコース", value=45),
        PieSlice(label="Bコース", value=30),
        PieSlice(label="Cコース", value=15),
        PieSlice(label="その他", value=10),
    ],
)


# ---- Composite (LLM designer style) -------------------------------------


# A more realistic "what the LLM would assemble" — title text, KPI
# pills, plus a chart. Demonstrates that the designer can mix
# primitives.
def _kpi_dashboard_spec() -> LayoutSpec:
    pills = [
        ("売上", "20.1億", "+34%", "primary"),
        ("MAU", "52,000", "+5.4×", "amber"),
        ("CVR", "4.8%", "+0.7pt", "green"),
        ("解約率", "1.2%", "-0.4pt", "muted"),
    ]
    pill_w = (BODY_W - 200_000) // len(pills)
    shapes: list[object] = []
    for i, (label, value, delta, color) in enumerate(pills):
        px = BODY_X + 100_000 + i * pill_w
        py = BODY_Y + 100_000
        shapes.extend(
            [
                RectShape(
                    name=f"kpi_card_{i}",
                    x=px,
                    y=py,
                    w=pill_w - 100_000,
                    h=900_000,
                    fill="primary_bg",
                    corner_radius_pct=8,
                ),
                PillShape(
                    name=f"kpi_pill_{i}",
                    x=px + 60_000,
                    y=py + 60_000,
                    w=600_000,
                    h=180_000,
                    text=label,
                    fill=color,
                    text_color="white",
                    size_pt=9,
                ),
                TextShape(
                    name=f"kpi_value_{i}",
                    x=px + 60_000,
                    y=py + 280_000,
                    w=pill_w - 220_000,
                    h=380_000,
                    paragraphs=[
                        TextParagraphSpec(
                            runs=[
                                TextRunSpec(
                                    text=value, size_pt=26, bold=True, color="text_dark"
                                )
                            ]
                        )
                    ],
                ),
                TextShape(
                    name=f"kpi_delta_{i}",
                    x=px + 60_000,
                    y=py + 680_000,
                    w=pill_w - 220_000,
                    h=180_000,
                    paragraphs=[
                        TextParagraphSpec(
                            runs=[TextRunSpec(text=delta, size_pt=11, color="muted")]
                        )
                    ],
                ),
            ]
        )
    shapes.append(
        BarChartShape(
            name="dash_trend",
            x=BODY_X + 100_000,
            y=BODY_Y + 1_100_000,
            w=BODY_W - 200_000,
            h=BODY_H - 1_300_000,
            series=[
                BarSeries(name="2023", values=[80, 95, 110, 130], color="muted"),
                BarSeries(name="2024", values=[120, 145, 168, 201], color="primary"),
            ],
            categories=["Q1", "Q2", "Q3", "Q4"],
            mode="grouped",
            orientation="v",
            show_values=True,
        )
    )
    return LayoutSpec(slide_index=1, shapes=shapes)  # type: ignore[arg-type]


def _comparison_table_spec() -> LayoutSpec:
    return LayoutSpec(
        slide_index=1,
        shapes=[
            TextShape(
                name="lead_text",
                x=BODY_X + 200_000,
                y=BODY_Y + 100_000,
                w=BODY_W - 400_000,
                h=400_000,
                paragraphs=[
                    TextParagraphSpec(
                        runs=[
                            TextRunSpec(
                                text="新プランは全機能セットの中で最も低コスト",
                                size_pt=14,
                                bold=True,
                                color="text_dark",
                            )
                        ]
                    )
                ],
            ),
            TableShape(
                name="plan_compare",
                x=BODY_X + 200_000,
                y=BODY_Y + 600_000,
                w=BODY_W - 400_000,
                h=BODY_H - 800_000,
                rows=[
                    ["項目", "Free", "Standard", CellSpec(text="Pro (新)", fill="primary", text_color="white")],
                    ["月額料金", "0円", "5,000円", CellSpec(text="9,800円", bold=True)],
                    ["ストレージ", "5GB", "100GB", CellSpec(text="無制限", bold=True)],
                    ["サポート", "FAQ のみ", "メール", CellSpec(text="24/7 電話 + メール", bold=True)],
                    ["SLA", "—", "99.5%", CellSpec(text="99.99%", bold=True)],
                ],
                columns=[
                    ColumnSpec(weight=2, align="l"),
                    ColumnSpec(weight=1, align="ctr"),
                    ColumnSpec(weight=1, align="ctr"),
                    ColumnSpec(weight=1, align="ctr"),
                ],
                header=True,
                alt_row_bg=True,
            ),
        ],
    )


# ---- Catalog -------------------------------------------------------------


SAMPLES: list[Sample] = [
    Sample(
        id="basic_quarterly",
        figure_type="table",
        title="四半期業績テーブル",
        prompt="四半期ごとの売上・利益・利益率を表でまとめたい",
        spec=LayoutSpec(slide_index=1, shapes=[_TABLE_BASIC]),
        notes="ヘッダ行 + 行交互背景 + 列重み 2:1:1:1:1。",
    ),
    Sample(
        id="col_span_header",
        figure_type="table",
        title="グルーピングヘッダのテーブル",
        prompt="セグメント別業績で、最上行に '2024年度通期業績' を 4 列まとめたい",
        spec=LayoutSpec(slide_index=1, shapes=[_TABLE_COL_SPAN]),
        notes="col_span でヘッダ統合。負値セルを amber でハイライト。",
    ),
    Sample(
        id="row_span_categories",
        figure_type="table",
        title="カテゴリ縦結合のテーブル",
        prompt="顧客獲得/維持カテゴリごとに複数施策をまとめた表。カテゴリは縦結合",
        spec=LayoutSpec(slide_index=1, shapes=[_TABLE_ROW_SPAN]),
        notes="row_span でカテゴリセルを縦結合。",
    ),
    Sample(
        id="quarterly_v",
        figure_type="bar_chart",
        title="四半期売上 (縦棒)",
        prompt="四半期売上のシンプルな縦棒グラフ",
        spec=LayoutSpec(slide_index=1, shapes=[_BAR_SIMPLE_V]),
        notes="単系列・縦棒・値ラベル付き。",
    ),
    Sample(
        id="region_share_h",
        figure_type="bar_chart",
        title="地域別シェア (横棒)",
        prompt="地域別売上構成比を横棒で並べたい",
        spec=LayoutSpec(slide_index=1, shapes=[_BAR_SIMPLE_H]),
        notes="単系列・横棒・パーセント書式。",
    ),
    Sample(
        id="yoy_grouped",
        figure_type="bar_chart",
        title="前年比較 (グループ棒)",
        prompt="2023 vs 2024 の四半期売上を年並びで比較したい",
        spec=LayoutSpec(slide_index=1, shapes=[_BAR_GROUPED_V]),
        notes="多系列 grouped。",
    ),
    Sample(
        id="channel_stacked",
        figure_type="bar_chart",
        title="チャネル積上げ",
        prompt="販売チャネル (自社EC/モール/店舗) の積上げ売上",
        spec=LayoutSpec(slide_index=1, shapes=[_BAR_STACKED_V]),
        notes="多系列 stacked。総量を比較。",
    ),
    Sample(
        id="cost_mix_pct",
        figure_type="bar_chart",
        title="コスト構成比 100%",
        prompt="原価構成比の年次推移を 100% 積上げで",
        spec=LayoutSpec(slide_index=1, shapes=[_BAR_STACKED100_V]),
        notes="多系列 stacked100。各年合計 100%。",
    ),
    Sample(
        id="mau_trend",
        figure_type="line_chart",
        title="MAU 推移",
        prompt="月次 MAU の伸びを折れ線で",
        spec=LayoutSpec(slide_index=1, shapes=[_LINE_SINGLE]),
        notes="単系列・マーカー付き。",
    ),
    Sample(
        id="kpi_trend",
        figure_type="line_chart",
        title="売上/原価/粗利の月次推移",
        prompt="売上・原価・粗利の 3 本を月別に重ねて推移を見たい",
        spec=LayoutSpec(slide_index=1, shapes=[_LINE_MULTI]),
        notes="3 系列・色分け。",
    ),
    Sample(
        id="market_share",
        figure_type="pie_chart",
        title="コース別シェア",
        prompt="A/B/C コースとその他の構成比",
        spec=LayoutSpec(slide_index=1, shapes=[_PIE_BASIC]),
        notes="4 スライス。ラベルは外側に手で添える運用。",
    ),
    Sample(
        id="kpi_dashboard",
        figure_type="composite",
        title="KPI ダッシュボード",
        prompt="売上・MAU・CVR・解約率を上段にカード、下段に YoY 棒グラフでまとめたダッシュボード",
        spec=_kpi_dashboard_spec(),
        notes="rect + pill + text + bar_chart の組合せ。",
    ),
    Sample(
        id="plan_comparison",
        figure_type="composite",
        title="プラン比較表",
        prompt="Free/Standard/Pro のプラン比較。Pro 列をハイライト",
        spec=_comparison_table_spec(),
        notes="text + table + ヘッダ列ハイライト + bold セル。",
    ),
    # ---- figure_renderer presets (deterministic) -----------------------
    Sample(
        id="timeline_basic",
        figure_type="timeline",
        title="導入ロードマップ",
        prompt="3〜6 ステップの工程をタイムライン状に並べたい",
        figure_content={
            "steps": [
                {"label": "1ヶ月目", "body": "現状アセスメント・要件定義"},
                {"label": "2ヶ月目", "body": "プロトタイプ構築 / PoC"},
                {"label": "3ヶ月目", "body": "本実装 / データ移行"},
                {"label": "4ヶ月目", "body": "現場検証・トレーニング"},
                {"label": "5ヶ月目", "body": "本番展開 / モニタリング"},
            ],
        },
        notes="figure_renderer の timeline プリセット。横並びノード。",
    ),
    Sample(
        id="comparison_before_after",
        figure_type="comparison",
        title="導入前後の業務フロー比較",
        prompt="現状(課題)と導入後(改善) を 2 カラムで対比",
        figure_content={
            "left": {
                "title": "現状",
                "items": [
                    "手作業で集計に 5 日",
                    "Excel が秘伝化、属人化",
                    "経営報告まで 1 週間遅れる",
                ],
            },
            "right": {
                "title": "導入後",
                "items": [
                    "自動集計で当日中に確定",
                    "ダッシュボード共通化",
                    "リアルタイム経営判断",
                ],
            },
        },
        notes="comparison の左右カラム。",
    ),
    Sample(
        id="kpi_dashboard_preset",
        figure_type="kpi_dashboard",
        title="KPI 一覧 (preset)",
        prompt="売上 / 満足度 / 応答速度の 3 KPI を上段に並べたい",
        figure_content={
            "metrics": [
                {"value": "20.1億", "label": "売上", "delta": "+34% YoY"},
                {"value": "85%", "label": "満足度", "delta": "+3pt"},
                {"value": "1.2s", "label": "応答", "delta": "-0.4s"},
            ],
        },
        notes="figure_renderer の kpi_dashboard プリセット。",
    ),
    Sample(
        id="stat_callout_growth",
        figure_type="stat_callout",
        title="成長率の強調",
        prompt="重要な数値 1 つを大きく出したい",
        figure_content={
            "value": "42%",
            "label": "前年同期比成長率",
            "note": "競合平均 12% を大きく上回る",
        },
        notes="単一数値の強調レイアウト。",
    ),
    Sample(
        id="icon_list_value_props",
        figure_type="icon_list",
        title="サービスの 4 つの価値",
        prompt="アイコン付きで価値を 3〜4 個並べたい",
        figure_content={
            "items": [
                {"icon": "✓", "title": "短納期", "body": "標準 4 週間で稼働"},
                {"icon": "✓", "title": "低リスク", "body": "段階導入で投資抑制"},
                {"icon": "✓", "title": "拡張性", "body": "他システムと API 連携"},
                {"icon": "✓", "title": "サポート", "body": "24/7 オンコール"},
            ],
        },
        notes="figure_renderer の icon_list プリセット。",
    ),
    Sample(
        id="stack_bar_revenue",
        figure_type="stack_bar",
        title="製品別四半期売上 (積上げ)",
        prompt="製品別の四半期売上を積上げ棒グラフで表現",
        figure_content={
            "categories": ["Q1", "Q2", "Q3", "Q4"],
            "series": [
                {"name": "コア", "values": [120, 145, 168, 201]},
                {"name": "新規", "values": [40, 55, 80, 120]},
                {"name": "保守", "values": [80, 82, 85, 90]},
            ],
        },
        notes="figure_renderer の stack_bar (LayoutSpec の bar_chart stacked と異なる実装)。",
    ),
    Sample(
        id="pull_quote_voice",
        figure_type="pull_quote",
        title="経営層からの一言",
        prompt="顧客や経営層の声を引用文として大きく見せたい",
        figure_content={
            "quote": "全社で意思決定スピードが 3 倍になった。これがいわゆる DX なのだと実感している。",
            "attribution": "A 社 取締役 CIO",
        },
        notes="引用 + 出典のレイアウト。",
    ),
    Sample(
        id="pyramid_strategy",
        figure_type="pyramid",
        title="戦略ピラミッド",
        prompt="ビジョン/戦略/施策の 3 階層を頂点から底辺で表現",
        figure_content={
            "levels": [
                {"label": "ビジョン", "body": "業界 No.1 のデータ駆動企業"},
                {"label": "戦略", "body": "全社データ統合・AI 活用基盤"},
                {"label": "施策", "body": "DWH 統合 / BI 整備 / 人材育成"},
            ],
        },
        notes="3 階層ピラミッド。",
    ),
    Sample(
        id="two_column_overview",
        figure_type="two_column",
        title="提案概要 (2 カラム)",
        prompt="左右 2 カラムで概要と詳細を並列に",
        figure_content={
            "left": {
                "title": "目的",
                "body": (
                    "全社の意思決定スピードを引き上げるため、"
                    "業務データをリアルタイムで可視化する基盤を導入する。"
                ),
            },
            "right": {
                "title": "アプローチ",
                "body": (
                    "段階的導入:\n"
                    "1) 営業・財務データの統合\n"
                    "2) BI ダッシュボード提供\n"
                    "3) AI 予測モデル展開"
                ),
            },
        },
        notes="シンプルな 2 カラム。",
    ),
    Sample(
        id="cards_grid_features",
        figure_type="cards_grid",
        title="機能カード",
        prompt="主要機能を 6 個カード型グリッドで紹介",
        figure_content={
            "cards": [
                {"title": "リアルタイム連携", "body": "5 分以内のデータ反映"},
                {"title": "AI 予測", "body": "需要・離脱・故障を先読み"},
                {"title": "ノーコード設計", "body": "現場で画面を作成"},
                {"title": "監査ログ", "body": "全操作を 90 日保管"},
                {"title": "SSO", "body": "Azure AD / Okta 対応"},
                {"title": "API", "body": "REST + GraphQL 提供"},
            ],
            "columns": 3,
        },
        notes="figure_renderer の cards_grid (3 列)。",
    ),
    Sample(
        id="bullet_list_value",
        figure_type="bullet_list",
        title="採用すべき 5 つの理由",
        prompt="箇条書きで主張を簡潔に列挙",
        figure_content={
            "items": [
                "国内導入実績 50 社、業種横断",
                "稼働 4 週間の短期立ち上げ",
                {"text": "投資回収 12 ヶ月以内", "sub": "実績ベース、業界平均 24 ヶ月"},
                "国際標準のセキュリティ準拠",
                "24/7 国内サポート",
            ],
        },
        notes="bullet_list — sub 説明付き項目も対応。",
    ),
    Sample(
        id="swot_analysis",
        figure_type="swot",
        title="SWOT 分析",
        prompt="自社の強み弱み機会脅威を 4 象限で整理",
        figure_content={
            "strengths": {
                "items": ["国内シェア No.1", "強力なブランド", "豊富な顧客基盤"],
            },
            "weaknesses": {
                "items": ["デジタル投資の遅れ", "若手人材不足"],
            },
            "opportunities": {
                "items": ["DX 補助金の拡充", "新市場 (海外) 開拓"],
            },
            "threats": {
                "items": ["新興プレイヤー", "規制強化"],
            },
        },
        notes="SWOT の 2x2 グリッド。",
    ),
    Sample(
        id="matrix_2x2_priority",
        figure_type="matrix_2x2",
        title="優先度マトリクス",
        prompt="重要度 × 緊急度 のマトリクスでタスクを分類",
        figure_content={
            "axes": {"x": {"label": "緊急度"}, "y": {"label": "重要度"}},
            "quadrants": [
                {"title": "最優先", "body": "今期 KPI に直結"},
                {"title": "計画的に着手", "body": "来期投資判断"},
                {"title": "委譲", "body": "現場で運用判断"},
                {"title": "見送り", "body": "再検討は半年後"},
            ],
        },
        notes="matrix_2x2 — 4 象限テンプレート。",
    ),
    Sample(
        id="process_flow_basic",
        figure_type="process_flow",
        title="プロセスフロー",
        prompt="5 ステップの業務プロセスを矢印で繋ぎたい",
        figure_content={
            "steps": [
                {"label": "STEP 1", "body": "ヒアリング"},
                {"label": "STEP 2", "body": "現状分析"},
                {"label": "STEP 3", "body": "提案設計"},
                {"label": "STEP 4", "body": "PoC 実施"},
                {"label": "STEP 5", "body": "本格導入"},
            ],
        },
        notes="左→右の矢印付きステップ。",
    ),
    Sample(
        id="cost_breakdown_total",
        figure_type="cost_breakdown",
        title="費用内訳",
        prompt="プロジェクト費用の内訳を合計付きで表示",
        figure_content={
            "total": {"label": "プロジェクト総額", "amount": 12_000_000, "currency": "¥"},
            "items": [
                {"label": "ライセンス", "amount": 5_000_000},
                {"label": "導入支援", "amount": 4_500_000},
                {"label": "教育", "amount": 1_500_000},
                {"label": "予備費", "amount": 1_000_000},
            ],
        },
        notes="cost_breakdown — 合計と内訳項目。",
    ),
    Sample(
        id="gantt_quarter",
        figure_type="gantt",
        title="四半期スケジュール",
        prompt="14 週のプロジェクトを 6 タスクのガントチャートで表示",
        figure_content={
            "total_weeks": 14,
            "tasks": [
                {"label": "要件定義", "start_week": 0, "end_week": 2},
                {"label": "基本設計", "start_week": 2, "end_week": 4},
                {"label": "詳細設計", "start_week": 3, "end_week": 5},
                {"label": "実装", "start_week": 5, "end_week": 10},
                {"label": "テスト", "start_week": 9, "end_week": 12},
                {"label": "リリース", "start_week": 12, "end_week": 14},
            ],
        },
        notes="ガントチャート — 重なりも表現可能。",
    ),
    Sample(
        id="waterfall_pl",
        figure_type="waterfall",
        title="売上→利益のウォーターフォール",
        prompt="売上から各コストを差し引いて営業利益に至るブリッジ",
        figure_content={
            "start": {"label": "売上", "value": 1000},
            "changes": [
                {"label": "原価", "value": -450},
                {"label": "販管費", "value": -300},
                {"label": "その他費用", "value": -100},
            ],
            "end": {"label": "営業利益", "value": 150},
        },
        notes="ウォーターフォール — 増減ブリッジ。",
    ),
    Sample(
        id="org_chart_team",
        figure_type="org_chart",
        title="プロジェクト体制",
        prompt="責任者→PM→各チームの体制を組織図で表現",
        figure_content={
            "nodes": [
                {"id": "po", "label": "PO", "role": "意思決定責任者", "members": "1名"},
                {
                    "id": "pm",
                    "label": "PM",
                    "parent": "po",
                    "role": "進行統括",
                    "members": "1名",
                },
                {
                    "id": "design",
                    "label": "設計チーム",
                    "parent": "pm",
                    "role": "業務設計",
                    "members": "3名",
                },
                {
                    "id": "dev",
                    "label": "開発チーム",
                    "parent": "pm",
                    "role": "実装",
                    "members": "5名",
                },
                {
                    "id": "qa",
                    "label": "QA チーム",
                    "parent": "pm",
                    "role": "品質保証",
                    "members": "2名",
                },
            ],
        },
        notes="org_chart — parent 参照ツリー。",
    ),
]
