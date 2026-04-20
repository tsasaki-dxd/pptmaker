#!/usr/bin/env python3
"""Part 3: slide8 (セクション扉3) / slide14 / slide15"""
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
# slide8: セクション扉3
# ============================================================
replace_text(SLIDES_DIR / "slide8.xml", [
    ("SECTION  01", "SECTION  03"),
    ("セクションタイトル", "AIガバナンス・推進人材"),
    ("このセクションの概要を1〜2行で記述します。",
     "将来のAI活用を見据え、まず利用規程・ガイドラインを整備。並行して社内AI推進担当者を育成し、自走できる組織へ。"),
    ("— 本セクションの読了目安 3分", "— スコープ: ご依頼事項 #8"),
    ("<a:t>03 / 06</a:t>", "<a:t>09 / 18</a:t>"),
])
print("slide8 done")

# ============================================================
# slide14: 生成AI利用規程・ガイドライン策定
# レイアウト: 左=コンセプト / 右=成果物カテゴリ5項目チェックリスト
# 下部=費用バー
# ============================================================
set_content_header(SLIDES_DIR / "slide14.xml",
                    "CONTENT ／ 05", "05 / AI",
                    "生成AI 利用規程・ガイドライン策定",
                    "PROJECT B", "10 / 18")

fig = []
sp = 100

left_x = inch(0.4)
body_y = inch(1.75)

# 左カラム: コンセプト
left_w = inch(4.2)
right_x = inch(4.9)
right_w = inch(4.7)

fig.append(text_box(sp, "l_t", left_x, body_y, left_w, inch(0.3),
                     "基本コンセプト",
                     size=1200, color=COLOR["black"], bold=True))
sp += 1
fig.append(h_line(sp, "l_ln", left_x, body_y + inch(0.38), left_w, COLOR["purple"], 19050))
sp += 1

# コンセプト対比: 禁止 vs 推進
ey = body_y + inch(0.6)
# 左半分(打ち消し線付き・薄字): 禁止するためのルール
fig.append(rect_shape(sp, "c_no_bg", left_x, ey, left_w, inch(0.7), COLOR["bg_alt"]))
sp += 1
fig.append(text_box(sp, "c_no_l", left_x + inch(0.2), ey + inch(0.1),
                     left_w - inch(0.4), inch(0.22),
                     "従来型（NG）", size=800, color=COLOR["muted"],
                     bold=True, font=FONT_MONO, spacing=150))
sp += 1
fig.append(text_box(sp, "c_no_t", left_x + inch(0.2), ey + inch(0.35),
                     left_w - inch(0.4), inch(0.3),
                     "禁止するためのルール", size=1200, color=COLOR["muted"], bold=True))
sp += 1

# 当社案
ey2 = ey + inch(0.9)
fig.append(rect_shape(sp, "c_ok_bg", left_x, ey2, left_w, inch(0.9), COLOR["purple"]))
sp += 1
fig.append(text_box(sp, "c_ok_l", left_x + inch(0.2), ey2 + inch(0.12),
                     left_w - inch(0.4), inch(0.22),
                     "当社アプローチ", size=800, color=COLOR["purple_lt"],
                     bold=True, font=FONT_MONO, spacing=150))
sp += 1
fig.append(text_box(sp, "c_ok_t", left_x + inch(0.2), ey2 + inch(0.38),
                     left_w - inch(0.4), inch(0.42),
                     "安全に推進するためのルール",
                     size=1400, color="FFFFFF", bold=True))
sp += 1

# 左下補足
fig.append(text_box_multi(sp, "l_supp", left_x, ey2 + inch(1.1), left_w, inch(0.7),
                           [("将来的なAI技術の発展と活用を見据え", {"size": 900, "color": COLOR["dark"]}),
                            ("まずは規程整備から段階的に着手します。", {"size": 900, "color": COLOR["dark"]})],
                           line_space_pct=140000))
sp += 1

# 右カラム: 主要成果物5項目
fig.append(text_box(sp, "r_t", right_x, body_y, right_w, inch(0.3),
                     "主要成果物",
                     size=1200, color=COLOR["black"], bold=True))
sp += 1
fig.append(h_line(sp, "r_ln", right_x, body_y + inch(0.38), right_w, COLOR["purple"], 19050))
sp += 1

deliverables = [
    ("01", "生成AI 利用ガイドライン／規程", "学園機密・個人情報・学生情報の取扱い区分"),
    ("02", "利用可能／不可ツール判定基準", "承認プロセスと対象ツール一覧"),
    ("03", "著作権・アウトプット責任ルール", "生成物の権利と学園としての責任範囲"),
    ("04", "インシデント対応フロー", "情報漏洩・誤出力時のエスカレーション"),
    ("05", "学内説明資料／研修資料", "プロジェクトCと連動した教材"),
]
dy = body_y + inch(0.55)
for i, (num, head, desc) in enumerate(deliverables):
    y = dy + i * inch(0.5)
    # 番号
    fig.append(text_box(sp, f"d_n_{i}", right_x, y, inch(0.3), inch(0.3),
                         num, size=900, color=COLOR["purple"], bold=True,
                         font=FONT_MONO))
    sp += 1
    # 見出し
    fig.append(text_box(sp, f"d_h_{i}", right_x + inch(0.4), y - inch(0.02),
                         right_w - inch(0.4), inch(0.25),
                         head, size=1050, color=COLOR["black"], bold=True))
    sp += 1
    # 説明
    fig.append(text_box(sp, f"d_d_{i}", right_x + inch(0.4), y + inch(0.22),
                         right_w - inch(0.4), inch(0.22),
                         desc, size=800, color=COLOR["dark"]))
    sp += 1

# 下部: 費用バー (スライド下端)
box_y = inch(4.92)
fig.append(rect_shape(sp, "cb_bg", inch(0.4), box_y, inch(9.2), inch(0.35), COLOR["purple"]))
sp += 1
fig.append(text_box(sp, "cb_t", inch(0.6), box_y, inch(9.0), inch(0.35),
                     "PROJECT B  想定期間 / 工数 / 費用（標準シナリオ）    2〜3ヶ月  ／  123h  ／  ¥1,230,000",
                     size=950, color="FFFFFF", bold=True, anchor_ctr=True,
                     font=FONT_MONO, spacing=50))
sp += 1

replace_body_with_figure(SLIDES_DIR / "slide14.xml", "\n".join(fig))
print("slide14 done (concept+checklist)")

# ============================================================
# slide15: AI推進人材育成プログラム (6ヶ月タイムライン)
# ============================================================
set_content_header(SLIDES_DIR / "slide15.xml",
                    "CONTENT ／ 06", "06 / AI",
                    "社内AI推進担当者 育成プログラム",
                    "PROJECT C", "11 / 18")

fig = []
sp = 100

left_x = inch(0.4)
body_y = inch(1.75)

# 冒頭のねらい
fig.append(text_box(sp, "intro", left_x, body_y, inch(9.2), inch(0.35),
                     "AI活用を各部署で自走できる「社内リーダー（DXチャンピオン）」を育成し、現場発の改善サイクルを回せる組織へ。",
                     size=1000, color=COLOR["dark"]))
sp += 1
fig.append(h_line(sp, "ln_i", left_x, body_y + inch(0.55), inch(9.2),
                   COLOR["border"], 6350))
sp += 1

# 6ヶ月タイムライン
# 全体領域: x=0.4, y=2.5, w=9.2, h=2.2
tl_y = inch(2.45)
tl_w = inch(9.2)
month_w = tl_w / 6

# 月ラベル行
for i in range(6):
    mx = left_x + month_w * i
    fig.append(text_box(sp, f"m_lbl_{i}", mx, tl_y, month_w, inch(0.3),
                         f"Month {i+1}", size=900, color=COLOR["purple"],
                         bold=True, align="c", font=FONT_MONO, spacing=100))
    sp += 1

# 軸 (月ラベル下)
fig.append(h_line(sp, "axis", left_x, tl_y + inch(0.4), tl_w, COLOR["dark"], 12700))
sp += 1

# プログラム3行(バー形式)
programs = [
    ("AI基礎研修", "全社向け・半日〜1日", 0, 2, COLOR["purple"]),  # M1-M2
    ("プロンプト実践研修", "部門別（経理・人事・学事・総務）", 1, 3, COLOR["purple"]),  # M2-M4
    ("推進担当者 月次セッション", "活用事例展開／AI倫理／ベンダー管理", 0, 6, COLOR["purple_dk"]),  # M1-M6
    ("フォローアップ＆ナレッジ化", "学園内AI活用事例集", 4, 2, COLOR["purple_lt"]),  # M5-M6
]
bar_h = inch(0.32)
gap = inch(0.08)
bar_y0 = tl_y + inch(0.55)

for i, (name, desc, start, length, color) in enumerate(programs):
    by = bar_y0 + i * (bar_h + gap)
    bx = left_x + month_w * start
    bw = month_w * length
    # バー
    fig.append(rect_shape(sp, f"b_{i}", bx, by, bw, bar_h, color))
    sp += 1
    # バー内テキスト
    tx_color = "FFFFFF" if color != COLOR["purple_lt"] else COLOR["black"]
    fig.append(text_box(sp, f"b_t_{i}", bx + inch(0.2), by, bw - inch(0.3), bar_h,
                         name, size=950, color=tx_color, bold=True,
                         anchor_ctr=True))
    sp += 1
    # 右側説明 (バー終端の右に表示できるスペースがあれば)
    desc_x = bx + bw + inch(0.15)
    desc_w = (left_x + tl_w) - desc_x
    if desc_w > inch(1.2):
        fig.append(text_box(sp, f"b_d_{i}", desc_x, by, desc_w, bar_h,
                             desc, size=850, color=COLOR["dark"], anchor_ctr=True))
        sp += 1

# 下部の費用バー
box_y = inch(4.92)
fig.append(rect_shape(sp, "cb_bg", left_x, box_y, inch(9.2), inch(0.35), COLOR["purple"]))
sp += 1
fig.append(text_box(sp, "cb_t", left_x + inch(0.2), box_y, inch(9.0), inch(0.35),
                     "PROJECT C  想定期間 / 工数 / 費用（標準シナリオ）    6ヶ月  ／  216h  ／  ¥2,160,000  （単発研修のみなら ¥50,000〜 / 日）",
                     size=900, color="FFFFFF", bold=True, anchor_ctr=True,
                     font=FONT_MONO, spacing=50))
sp += 1

replace_body_with_figure(SLIDES_DIR / "slide15.xml", "\n".join(fig))
print("slide15 done (timeline)")

print("\n=== Part 3 done ===")
