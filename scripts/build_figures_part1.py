#!/usr/bin/env python3
"""
図表付きの提案書を生成するメインスクリプト。
各コンテンツスライドから本文テキスト要素(Text 5, Text 6)を削除し、
代わりに表・カード・タイムラインなどの図表XMLを挿入する。
"""
import re
from pathlib import Path
from shape_lib import (COLOR, FONT_JP, FONT_MONO, inch, pt,
                        rect_shape, rect_outline, text_box, text_box_multi,
                        pill_label, h_line)

SLIDES_DIR = Path("/home/claude/template_unpacked/ppt/slides")

# ============================================================
# ヘルパー: 本文領域(Text 5 + Text 6)を削除し、図表XMLに置き換え
# ============================================================
def replace_body_with_figure(slide_path: Path, figure_xml: str):
    """slide4系コンテンツスライドのText 5, Text 6を削除してfigure_xmlを差し込む"""
    content = slide_path.read_text(encoding="utf-8")
    # Text 5 削除 (id="8" name="Text 5")
    pattern5 = re.compile(
        r'<p:sp>\s*<p:nvSpPr>\s*<p:cNvPr id="8" name="Text 5"/>.*?</p:sp>',
        re.DOTALL)
    content = pattern5.sub("", content, count=1)
    # Text 6 削除 (id="9" name="Text 6")
    pattern6 = re.compile(
        r'<p:sp>\s*<p:nvSpPr>\s*<p:cNvPr id="9" name="Text 6"/>.*?</p:sp>',
        re.DOTALL)
    content = pattern6.sub("", content, count=1)
    # </p:spTree> の直前に figure_xml を挿入
    content = content.replace("</p:spTree>", figure_xml + "\n    </p:spTree>", 1)
    slide_path.write_text(content, encoding="utf-8")


# ============================================================
# 基本テキスト置換 (ヘッダー/タイトルなど既存部分の編集用)
# ============================================================
def replace_text(slide_path: Path, replacements: list):
    c = slide_path.read_text(encoding="utf-8")
    for old, new in replacements:
        if old in c:
            c = c.replace(old, new, 1)
        else:
            print(f"  [WARN] {slide_path.name}: '{old[:30]}' not found")
    slide_path.write_text(c, encoding="utf-8")


def set_content_header(path, top_label, title_label, title, body_label, page):
    """コンテンツスライドのヘッダー・タイトル・BODYラベル・ページ番号を差替"""
    c = path.read_text(encoding="utf-8")
    # 1つ目のCONTENT = 左上ラベル
    c = c.replace("<a:t>CONTENT</a:t>", f"<a:t>{top_label}</a:t>", 1)
    # 2つ目のCONTENT = タイトル左紫ラベル  
    c = c.replace("<a:t>CONTENT</a:t>", f"<a:t>{title_label}</a:t>", 1)
    c = c.replace("コンテンツタイトル", title)
    c = c.replace("<a:t>BODY</a:t>", f"<a:t>{body_label}</a:t>")
    c = c.replace("<a:t>04 / 06</a:t>", f"<a:t>{page}</a:t>")
    path.write_text(c, encoding="utf-8")


# ============================================================
# slide1: 表紙
# ============================================================
replace_text(SLIDES_DIR / "slide1.xml", [
    ("YYYY.MM.DD", "2026.04.16"),
    ("PRESENTATION ／ COVER", "PROPOSAL ／ DX &amp; AI SUPPORT"),
    ("タイトルを", "DX推進・AI活用"),
    ("ここに入れる。", "ご提案書"),
    ("サブタイトル・コンセプト文を1〜2行で。", "発注者側に立った中立的な伴走支援  ／  学園法人 御中"),
])
print("slide1 done")

# ============================================================
# slide2: 目次
# ============================================================
s2 = SLIDES_DIR / "slide2.xml"
c = s2.read_text(encoding="utf-8")
for new_title in ["ご依頼の整理と全体像", "業務プロセス改善支援",
                   "統合DB・共通マスタ設計", "AIガバナンス・推進人材",
                   "費用・スケジュール・体制"]:
    c = c.replace("項目タイトル", new_title, 1)
for new_sec in ["Request &amp; Scope", "Process Improvement",
                 "Data &amp; Master Design", "AI Governance",
                 "Cost &amp; Schedule"]:
    c = c.replace("Section title", new_sec, 1)
c = c.replace("本資料の構成を以下の順で説明します。",
              "本ご提案の構成を以下の順に沿ってご説明します。")
c = c.replace("<a:t>02 / 06</a:t>", "<a:t>02 / 18</a:t>", 1)
s2.write_text(c, encoding="utf-8")
print("slide2 done")

# ============================================================
# slide3: セクション扉1
# ============================================================
replace_text(SLIDES_DIR / "slide3.xml", [
    ("セクションタイトル", "業務プロセス改善支援"),
    ("このセクションの概要を1〜2行で記述します。",
     "現場課題への即効策と、エデュース社要件定義の並走レビューにより、To-Be業務フロー／システム／データフローを最適化します。"),
    ("— 本セクションの読了目安 3分", "— スコープ: ご依頼事項 #1〜#5"),
    ("<a:t>03 / 06</a:t>", "<a:t>03 / 18</a:t>"),
])
print("slide3 done")

# ============================================================
# slide10: ご依頼事項と契約形態の対応 (表形式)
# ============================================================
set_content_header(SLIDES_DIR / "slide10.xml",
                    "CONTENT ／ 01", "01 / MAP",
                    "ご依頼事項と契約形態の対応",
                    "REQUEST MAPPING", "04 / 18")

# 表: # / 依頼事項 / 契約形態 の 9行(ヘッダー含む)
tbl_x = inch(0.4)
tbl_y = inch(1.75)
tbl_w = inch(9.2)
row_h = inch(0.36)
col_w = [inch(0.5), inch(6.5), inch(2.2)]

rows = [
    ("#", "依頼事項", "契約形態", True, None),
    ("1", "To-Be業務フロー（業務一元化含む）のレビュー", "月額顧問", False, "green"),
    ("2", "To-Be業務フローに合わせたシステム構成のレビュー", "月額顧問", False, "green"),
    ("3", "To-Be業務フローに合わせたデータフローのレビュー", "月額顧問", False, "green"),
    ("4", "AI活用を含む業務効率化システム・サービスの情報提供", "月額顧問", False, "green"),
    ("5", "選定システムの要件定義とTo-Beフローとのギャップ解消", "月額顧問", False, "green"),
    ("6", "統合DB（特に経理領域）の構造設計に関する提案", "プロジェクト型", False, "amber"),
    ("7", "統合DB構築を見据えた学園共通コードのレビュー", "プロジェクト型", False, "amber"),
    ("8", "生成AIの利用規程・ガイドライン等のルール策定支援", "プロジェクト型", False, "amber"),
]

fig_parts = []
sp_id = 100
y_cur = tbl_y
for i, (num, req, ctype, is_header, ctag) in enumerate(rows):
    bg = COLOR["purple"] if is_header else (COLOR["white"] if i % 2 == 1 else COLOR["bg_alt"])
    txt_color = "FFFFFF" if is_header else COLOR["black"]
    # 行背景
    fig_parts.append(rect_shape(sp_id, f"row_bg_{i}", tbl_x, y_cur, tbl_w, row_h, bg))
    sp_id += 1
    # 列1: 番号
    fig_parts.append(text_box(sp_id, f"c1_{i}", tbl_x + inch(0.1), y_cur, col_w[0], row_h,
                               num, size=1000, color=txt_color, bold=is_header,
                               font=FONT_MONO if not is_header else FONT_JP,
                               align="c", anchor_ctr=True))
    sp_id += 1
    # 列2: 依頼事項
    fig_parts.append(text_box(sp_id, f"c2_{i}", tbl_x + col_w[0], y_cur, col_w[1], row_h,
                               req, size=1000, color=txt_color, bold=is_header,
                               anchor_ctr=True))
    sp_id += 1
    # 列3: 契約形態 (通常行はピル表示)
    if is_header:
        fig_parts.append(text_box(sp_id, f"c3_{i}", tbl_x + col_w[0] + col_w[1], y_cur,
                                   col_w[2], row_h, ctype,
                                   size=1000, color=txt_color, bold=True,
                                   align="c", anchor_ctr=True))
        sp_id += 1
    else:
        pill_bg = COLOR["green"] if ctag == "green" else COLOR["amber"]
        pill_x = tbl_x + col_w[0] + col_w[1] + inch(0.3)
        pill_y = y_cur + inch(0.06)
        pill_w = inch(1.6)
        pill_h = inch(0.24)
        fig_parts.append(pill_label(sp_id, f"pill_{i}", pill_x, pill_y, pill_w, pill_h,
                                     ctype, bg_color=pill_bg, size=900, spacing=100))
        sp_id += 2
    y_cur += row_h

# 下部の凡例
legend_y = y_cur + inch(0.2)
fig_parts.append(rect_shape(sp_id, "legend_gr", tbl_x, legend_y, inch(0.16), inch(0.16), COLOR["green"]))
sp_id += 1
fig_parts.append(text_box(sp_id, "legend_gr_tx", tbl_x + inch(0.24), legend_y - inch(0.03),
                           inch(4.5), inch(0.22),
                           "月額顧問 ＝ 継続伴走（レビュー・情報提供・調整）",
                           size=900, color=COLOR["dark"]))
sp_id += 1
fig_parts.append(rect_shape(sp_id, "legend_am", tbl_x + inch(4.7), legend_y,
                             inch(0.16), inch(0.16), COLOR["amber"]))
sp_id += 1
fig_parts.append(text_box(sp_id, "legend_am_tx", tbl_x + inch(4.94), legend_y - inch(0.03),
                           inch(4.5), inch(0.22),
                           "プロジェクト型 ＝ 単発・成果物型（設計書・規程など）",
                           size=900, color=COLOR["dark"]))
sp_id += 1

replace_body_with_figure(SLIDES_DIR / "slide10.xml", "\n".join(fig_parts))
print("slide10 done (table)")

# ============================================================
# slide11: 貴学園の現状理解 (3カラムカード + 論点リスト)
# ============================================================
set_content_header(SLIDES_DIR / "slide11.xml",
                    "CONTENT ／ 02", "02 / NOW",
                    "貴学園の現状理解と主要論点（仮説）",
                    "CURRENT STATE", "05 / 18")

fig_parts = []
sp_id = 100

# 上段: 3カラムカード (人事/経理/共通)
card_y = inch(1.75)
card_h = inch(1.5)
card_w = inch(2.9)
gap = inch(0.15)
start_x = inch(0.4)

cards = [
    ("人事領域", "HR", "統合DB PJ 進行中", "パトスロゴス社と佐々木様のご紹介により実装フェーズへ。"),
    ("経理領域", "FINANCE", "要件定義これから", "エデュース社による業務要件定義を開始。\nDB構築方針は未確定。"),
    ("共通", "COMMON", "業務一元化を志向", "To-Be業務フローが一部定義された段階。一元化の方向性。"),
]

for i, (label, label_en, status, desc) in enumerate(cards):
    cx = start_x + (card_w + gap) * i
    # カード背景
    fig_parts.append(rect_shape(sp_id, f"card_{i}_bg", cx, card_y, card_w, card_h, COLOR["bg_alt"]))
    sp_id += 1
    # 左の紫縦ライン
    fig_parts.append(rect_shape(sp_id, f"card_{i}_ln", cx, card_y, inch(0.04), card_h, COLOR["purple"]))
    sp_id += 1
    # 英語ラベル
    fig_parts.append(text_box(sp_id, f"card_{i}_en", cx + inch(0.2), card_y + inch(0.15),
                               card_w - inch(0.2), inch(0.2), label_en,
                               size=800, color=COLOR["purple"], bold=True,
                               font=FONT_MONO, spacing=200))
    sp_id += 1
    # 日本語領域名
    fig_parts.append(text_box(sp_id, f"card_{i}_jp", cx + inch(0.2), card_y + inch(0.38),
                               card_w - inch(0.2), inch(0.35), label,
                               size=1600, color=COLOR["black"], bold=True))
    sp_id += 1
    # ステータスピル
    fig_parts.append(pill_label(sp_id, f"card_{i}_pill",
                                 cx + inch(0.2), card_y + inch(0.8),
                                 inch(2.0), inch(0.25),
                                 status, bg_color=COLOR["purple"], size=900, spacing=50))
    sp_id += 2
    # 説明文
    fig_parts.append(text_box_multi(sp_id, f"card_{i}_desc",
                                     cx + inch(0.2), card_y + inch(1.1),
                                     card_w - inch(0.4), inch(0.4),
                                     [(l, {"size": 850, "color": COLOR["dark"]}) for l in desc.split("\n")],
                                     line_space_pct=120000))
    sp_id += 1

# 下段: 主要論点
issues_y = inch(3.45)
fig_parts.append(text_box(sp_id, "issues_title", start_x, issues_y, inch(9.2), inch(0.3),
                           "当社が捉える主要論点",
                           size=1100, color=COLOR["black"], bold=True))
sp_id += 1
fig_parts.append(h_line(sp_id, "issues_line", start_x, issues_y + inch(0.35),
                         inch(9.2), COLOR["purple"], width=19050))
sp_id += 1

issues = [
    ("A", "「今すぐの打ち手」と「将来の統合DB・AI活用」の整合性確保"),
    ("B", "経理DB方針の不透明さが後工程のコード・マスタ・BIに波及するリスク"),
    ("C", "人事（パトスロゴス）× 経理（エデュース）のマスタ整合性"),
    ("D", "生成AI利用に関する学園統一ルールの未整備"),
]
iss_y = issues_y + inch(0.55)
for i, (tag, txt) in enumerate(issues):
    col = i % 2
    row = i // 2
    ix = start_x + col * inch(4.6)
    iy = iss_y + row * inch(0.35)
    # タグ付き丸
    fig_parts.append(rect_shape(sp_id, f"iss_tag_{i}", ix, iy + inch(0.02),
                                 inch(0.28), inch(0.28), COLOR["purple"]))
    sp_id += 1
    fig_parts.append(text_box(sp_id, f"iss_tag_tx_{i}", ix, iy + inch(0.02),
                               inch(0.28), inch(0.28), tag,
                               size=900, color="FFFFFF", bold=True,
                               align="c", anchor_ctr=True))
    sp_id += 1
    fig_parts.append(text_box(sp_id, f"iss_tx_{i}", ix + inch(0.4), iy,
                               inch(4.2), inch(0.32), txt,
                               size=950, color=COLOR["black"], anchor_ctr=True))
    sp_id += 1

replace_body_with_figure(SLIDES_DIR / "slide11.xml", "\n".join(fig_parts))
print("slide11 done (cards+issues)")

print("\n=== Part 1 done ===")
