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
    plausibly elicit this layout from the designer LLM."""

    id: str
    figure_type: str
    title: str
    prompt: str
    spec: LayoutSpec
    notes: str = ""


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
]
