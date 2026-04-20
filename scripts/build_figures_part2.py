#!/usr/bin/env python3
"""Part 2: slide7 (セクション扉2) / slide12 / slide13"""
import re
from pathlib import Path
from shape_lib import (COLOR, FONT_JP, FONT_MONO, inch, pt,
                        rect_shape, rect_outline, text_box, text_box_multi,
                        pill_label, h_line)

SLIDES_DIR = Path("/home/claude/template_unpacked/ppt/slides")

def replace_body_with_figure(slide_path, figure_xml):
    content = slide_path.read_text(encoding="utf-8")
    pattern5 = re.compile(r'<p:sp>\s*<p:nvSpPr>\s*<p:cNvPr id="8" name="Text 5"/>.*?</p:sp>', re.DOTALL)
    content = pattern5.sub("", content, count=1)
    pattern6 = re.compile(r'<p:sp>\s*<p:nvSpPr>\s*<p:cNvPr id="9" name="Text 6"/>.*?</p:sp>', re.DOTALL)
    content = pattern6.sub("", content, count=1)
    content = content.replace("</p:spTree>", figure_xml + "\n    </p:spTree>", 1)
    slide_path.write_text(content, encoding="utf-8")

def replace_text(slide_path, replacements):
    c = slide_path.read_text(encoding="utf-8")
    for old, new in replacements:
        if old in c:
            c = c.replace(old, new, 1)
    slide_path.write_text(c, encoding="utf-8")

def set_content_header(path, top_label, title_label, title, body_label, page):
    c = path.read_text(encoding="utf-8")
    c = c.replace("<a:t>CONTENT</a:t>", f"<a:t>{top_label}</a:t>", 1)
    c = c.replace("<a:t>CONTENT</a:t>", f"<a:t>{title_label}</a:t>", 1)
    c = c.replace("コンテンツタイトル", title)
    c = c.replace("<a:t>BODY</a:t>", f"<a:t>{body_label}</a:t>")
    c = c.replace("<a:t>04 / 06</a:t>", f"<a:t>{page}</a:t>")
    path.write_text(c, encoding="utf-8")


# ============================================================
# slide7: セクション扉2
# ============================================================
replace_text(SLIDES_DIR / "slide7.xml", [
    ("SECTION  01", "SECTION  02"),
    ("セクションタイトル", "統合DB・共通マスタ設計"),
    ("このセクションの概要を1〜2行で記述します。",
     "経理領域の統合DB構造設計と、人事（パトスロゴス）との整合を担保する学園共通マスタ整備を、発注者側PM視点でご支援します。"),
    ("— 本セクションの読了目安 3分", "— スコープ: ご依頼事項 #6〜#7"),
    ("<a:t>03 / 06</a:t>", "<a:t>06 / 18</a:t>"),
])
print("slide7 done")

# ============================================================
# slide12: 統合DB構造設計
# レイアウト: 左カラム「ねらい」3項目 / 右カラム「主要成果物＋費用」
# ============================================================
set_content_header(SLIDES_DIR / "slide12.xml",
                    "CONTENT ／ 03", "03 / DB",
                    "統合DB（経理領域）構造設計",
                    "PROJECT A", "07 / 18")

fig = []
sp = 100

# 左カラム: ねらい
left_x = inch(0.4)
right_x = inch(5.1)
body_y = inch(1.75)
col_w = inch(4.5)

# 左タイトル
fig.append(text_box(sp, "l_title", left_x, body_y, col_w, inch(0.3),
                     "本プロジェクトのねらい",
                     size=1200, color=COLOR["black"], bold=True))
sp += 1
fig.append(h_line(sp, "l_line", left_x, body_y + inch(0.38), col_w,
                   COLOR["purple"], 19050))
sp += 1

aims = [
    ("01", "業務要件 → DB構造への翻訳",
     "エデュース社の業務要件定義と並走し、発注者側でDB設計をコントロール"),
    ("02", "学園全体で単一のコード体系",
     "人事（パトスロゴス）とのマスタ整合性を確保し、横串の分析基盤を実現"),
    ("03", "将来の分析・BI・AI活用を見据える",
     "拡張性のあるDB設計で、5〜10年先まで活かせるデータ基盤を構築"),
]
ay = body_y + inch(0.6)
for i, (num, head, desc) in enumerate(aims):
    y = ay + i * inch(0.88)
    # 番号バッジ
    fig.append(rect_shape(sp, f"aim_n_{i}", left_x, y, inch(0.45), inch(0.45), COLOR["purple"]))
    sp += 1
    fig.append(text_box(sp, f"aim_n_tx_{i}", left_x, y, inch(0.45), inch(0.45),
                         num, size=1100, color="FFFFFF", bold=True,
                         align="c", anchor_ctr=True, font=FONT_MONO))
    sp += 1
    # 見出し
    fig.append(text_box(sp, f"aim_h_{i}", left_x + inch(0.6), y, col_w - inch(0.6), inch(0.3),
                         head, size=1100, color=COLOR["black"], bold=True))
    sp += 1
    # 説明
    fig.append(text_box_multi(sp, f"aim_d_{i}", left_x + inch(0.6), y + inch(0.32),
                               col_w - inch(0.6), inch(0.5),
                               [(desc, {"size": 900, "color": COLOR["dark"]})],
                               line_space_pct=120000))
    sp += 1

# 右カラム: 成果物
fig.append(text_box(sp, "r_title", right_x, body_y, col_w, inch(0.3),
                     "主要成果物",
                     size=1200, color=COLOR["black"], bold=True))
sp += 1
fig.append(h_line(sp, "r_line", right_x, body_y + inch(0.38), col_w,
                   COLOR["purple"], 19050))
sp += 1

deliverables = [
    "統合DB構造設計提案書（論理／物理モデル／ER図）",
    "クラウド・アーキテクチャ提案書（AWS/GCP/Azure比較・コスト試算）",
    "データガバナンス運用ルール案",
    "マスタ連携方式設計（ETL / ELT）",
]
dy = body_y + inch(0.6)
for i, txt in enumerate(deliverables):
    y = dy + i * inch(0.38)
    # チェックマーク代わりの四角
    fig.append(rect_shape(sp, f"del_b_{i}", right_x, y + inch(0.06),
                           inch(0.18), inch(0.18), COLOR["purple"]))
    sp += 1
    fig.append(text_box(sp, f"del_t_{i}", right_x + inch(0.3), y,
                         col_w - inch(0.3), inch(0.3),
                         txt, size=950, color=COLOR["black"], anchor_ctr=True))
    sp += 1

# 右下: 期間・費用サマリーボックス
box_y = inch(4.0)
fig.append(rect_shape(sp, "cost_bg", right_x, box_y, col_w, inch(0.9), COLOR["purple"]))
sp += 1
fig.append(text_box(sp, "cost_l1", right_x + inch(0.25), box_y + inch(0.12),
                     col_w - inch(0.5), inch(0.22),
                     "想定期間 / 工数 / 費用（標準シナリオ）",
                     size=800, color=COLOR["purple_lt"], bold=True,
                     spacing=100, font=FONT_MONO))
sp += 1
fig.append(text_box(sp, "cost_l2", right_x + inch(0.25), box_y + inch(0.40),
                     col_w - inch(0.5), inch(0.45),
                     "3〜4ヶ月  ／  244h  ／  ¥2,440,000",
                     size=1300, color="FFFFFF", bold=True))
sp += 1

replace_body_with_figure(SLIDES_DIR / "slide12.xml", "\n".join(fig))
print("slide12 done (2-column)")

# ============================================================
# slide13: 共通マスタレビュー
# レイアウト: 上段4マスカード（主要マスタ） / 下段 設計方針3点
# ============================================================
set_content_header(SLIDES_DIR / "slide13.xml",
                    "CONTENT ／ 04", "04 / DB",
                    "学園共通コード（共通マスタ）レビュー",
                    "COMMON MASTER", "08 / 18")

fig = []
sp = 100

# 上段タイトル
left_x = inch(0.4)
body_y = inch(1.75)

fig.append(text_box(sp, "mas_title", left_x, body_y, inch(9.2), inch(0.3),
                     "レビュー対象の主要マスタ",
                     size=1200, color=COLOR["black"], bold=True))
sp += 1
fig.append(h_line(sp, "mas_line", left_x, body_y + inch(0.38), inch(9.2),
                   COLOR["purple"], 19050))
sp += 1

# 4マスカード (2x2)
masters = [
    ("部門コード", "DEPARTMENT", "人事 × 経理 × 学事で横串に連携"),
    ("教職員コード", "FACULTY", "人事マスタを起点に全業務で一意化"),
    ("勘定科目", "ACCOUNT", "補助科目・セグメント設計と連動"),
    ("予算・取引先コード", "BUDGET / PARTNER", "採番ルール・改廃ルールのガバナンス設計"),
]
card_w = inch(4.5)
card_h = inch(1.0)
gap_x = inch(0.2)
gap_y = inch(0.12)
cy0 = body_y + inch(0.55)

for i, (jp, en, desc) in enumerate(masters):
    col = i % 2
    row = i // 2
    cx = left_x + col * (card_w + gap_x)
    cy = cy0 + row * (card_h + gap_y)
    # カード背景
    fig.append(rect_shape(sp, f"m_bg_{i}", cx, cy, card_w, card_h, COLOR["bg_alt"]))
    sp += 1
    # 左縦ライン
    fig.append(rect_shape(sp, f"m_ln_{i}", cx, cy, inch(0.05), card_h, COLOR["purple"]))
    sp += 1
    # 英語ラベル
    fig.append(text_box(sp, f"m_en_{i}", cx + inch(0.25), cy + inch(0.1),
                         card_w - inch(0.25), inch(0.2),
                         en, size=800, color=COLOR["purple"], bold=True,
                         font=FONT_MONO, spacing=200))
    sp += 1
    # 日本語名
    fig.append(text_box(sp, f"m_jp_{i}", cx + inch(0.25), cy + inch(0.32),
                         card_w - inch(0.3), inch(0.34),
                         jp, size=1400, color=COLOR["black"], bold=True))
    sp += 1
    # 説明
    fig.append(text_box(sp, f"m_d_{i}", cx + inch(0.25), cy + inch(0.7),
                         card_w - inch(0.3), inch(0.25),
                         desc, size=850, color=COLOR["dark"]))
    sp += 1

# 下段: 設計方針
policy_y = cy0 + 2 * (card_h + gap_y) + inch(0.15)
fig.append(text_box(sp, "p_title", left_x, policy_y, inch(9.2), inch(0.28),
                     "設計方針",
                     size=1200, color=COLOR["black"], bold=True))
sp += 1
fig.append(h_line(sp, "p_line", left_x, policy_y + inch(0.34), inch(9.2),
                   COLOR["purple"], 19050))
sp += 1

policies = [
    "採番ルール／改廃ルールのガバナンス設計",
    "パトスロゴス側成果物との整合レビュー",
    "DWH／データマート／BI配置方針",
]
py = policy_y + inch(0.5)
for i, txt in enumerate(policies):
    x = left_x + i * inch(3.1)
    fig.append(rect_shape(sp, f"p_n_bg_{i}", x, py, inch(0.3), inch(0.3), COLOR["purple"]))
    sp += 1
    fig.append(text_box(sp, f"p_n_{i}", x, py, inch(0.3), inch(0.3),
                         f"0{i+1}", size=850, color="FFFFFF", bold=True,
                         align="c", anchor_ctr=True, font=FONT_MONO))
    sp += 1
    fig.append(text_box(sp, f"p_t_{i}", x + inch(0.4), py, inch(2.7), inch(0.3),
                         txt, size=900, color=COLOR["black"], anchor_ctr=True))
    sp += 1

replace_body_with_figure(SLIDES_DIR / "slide13.xml", "\n".join(fig))
print("slide13 done (master cards)")

print("\n=== Part 2 done ===")
