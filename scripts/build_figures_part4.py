#!/usr/bin/env python3
"""Part 4: slide9 (セクション扉4) / slide16 / slide17 / slide18 / slide4 (Next Steps)"""
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
# slide9: セクション扉4
# ============================================================
replace_text(SLIDES_DIR / "slide9.xml", [
    ("SECTION  01", "SECTION  04"),
    ("セクションタイトル", "費用・スケジュール・体制"),
    ("このセクションの概要を1〜2行で記述します。",
     "月額顧問（継続伴走）とプロジェクト型（単発成果物）を組み合わせた現実的な構成と、12ヶ月想定のトータルコストをご提示します。"),
    ("— 本セクションの読了目安 3分", "— スコープ: 工数積み上げ／費用／次のステップ"),
    ("<a:t>03 / 06</a:t>", "<a:t>12 / 18</a:t>"),
])
print("slide9 done")

# ============================================================
# slide16: 月額顧問 工数積み上げ
# レイアウト: 左=アクティビティ別工数表、右=シナリオ比較の大数字
# ============================================================
set_content_header(SLIDES_DIR / "slide16.xml",
                    "CONTENT ／ 07", "07 / COST",
                    "月額顧問  工数積み上げ",
                    "RETAINER EFFORT", "13 / 18")

fig = []
sp = 100

left_x = inch(0.4)
body_y = inch(1.75)

# 左カラム: アクティビティ別工数表
left_w = inch(5.6)
right_x = inch(6.2)
right_w = inch(3.4)

fig.append(text_box(sp, "l_t", left_x, body_y, left_w, inch(0.3),
                     "主要アクティビティ別  月次工数（標準シナリオ）",
                     size=1100, color=COLOR["black"], bold=True))
sp += 1
fig.append(h_line(sp, "l_ln", left_x, body_y + inch(0.38), left_w, COLOR["purple"], 19050))
sp += 1

# ヘッダー
tbl_y = body_y + inch(0.55)
row_h = inch(0.42)
# ヘッダー行
fig.append(text_box(sp, "h_1", left_x + inch(0.1), tbl_y,
                     inch(0.5), row_h, "#", size=800,
                     color=COLOR["muted"], bold=True,
                     font=FONT_MONO, anchor_ctr=True))
sp += 1
fig.append(text_box(sp, "h_2", left_x + inch(0.6), tbl_y,
                     inch(3.8), row_h, "アクティビティ",
                     size=800, color=COLOR["muted"], bold=True,
                     font=FONT_MONO, anchor_ctr=True, spacing=100))
sp += 1
fig.append(text_box(sp, "h_3", left_x + inch(4.4), tbl_y,
                     inch(1.1), row_h, "工数 / 月",
                     size=800, color=COLOR["muted"], bold=True,
                     font=FONT_MONO, anchor_ctr=True, align="r", spacing=100))
sp += 1

activities = [
    ("A", "現場課題起点の即効支援", "10.0 h"),
    ("B", "To-Beフロー／システム／データフロー レビュー", "12.0 h"),
    ("C", "エデュース要件定義並走・ベンダー調整", "16.0 h"),
    ("D", "AI・業務効率化ツール情報提供・MTG運営", "17.0 h"),
]
for i, (tag, name, hrs) in enumerate(activities):
    y = tbl_y + (i + 1) * row_h
    # タグ
    fig.append(rect_shape(sp, f"tag_bg_{i}", left_x + inch(0.1), y + inch(0.07),
                           inch(0.32), inch(0.28), COLOR["purple"]))
    sp += 1
    fig.append(text_box(sp, f"tag_{i}", left_x + inch(0.1), y + inch(0.07),
                         inch(0.32), inch(0.28), tag, size=850, color="FFFFFF",
                         bold=True, align="c", anchor_ctr=True, font=FONT_MONO))
    sp += 1
    # 名前
    fig.append(text_box(sp, f"nm_{i}", left_x + inch(0.6), y,
                         inch(3.8), row_h, name, size=950, color=COLOR["black"],
                         anchor_ctr=True))
    sp += 1
    # 工数
    fig.append(text_box(sp, f"hr_{i}", left_x + inch(4.4), y,
                         inch(1.1), row_h, hrs, size=1050, color=COLOR["black"],
                         bold=True, align="r", anchor_ctr=True, font=FONT_MONO))
    sp += 1

# 合計行 (紫帯)
sum_y = tbl_y + 5 * row_h + inch(0.1)
fig.append(rect_shape(sp, "sum_bg", left_x, sum_y, left_w, inch(0.5), COLOR["purple"]))
sp += 1
fig.append(text_box(sp, "sum_l", left_x + inch(0.2), sum_y,
                     inch(3.8), inch(0.5), "月次合計",
                     size=1000, color="FFFFFF", bold=True, anchor_ctr=True))
sp += 1
fig.append(text_box(sp, "sum_v", left_x + inch(4.0), sum_y,
                     inch(1.5), inch(0.5), "55.0 h / 月",
                     size=1400, color="FFFFFF", bold=True, align="r",
                     anchor_ctr=True, font=FONT_MONO))
sp += 1

# 右カラム: シナリオ比較
fig.append(text_box(sp, "r_t", right_x, body_y, right_w, inch(0.3),
                     "シナリオ比較",
                     size=1100, color=COLOR["black"], bold=True))
sp += 1
fig.append(h_line(sp, "r_ln", right_x, body_y + inch(0.38), right_w, COLOR["purple"], 19050))
sp += 1

scenarios = [
    ("控えめ", "31.5 h", "900"),   # (label, value, size)
    ("標準（推奨）", "55.0 h", "1000"),
    ("手厚い", "86.0 h", "900"),
]
sy = body_y + inch(0.55)
for i, (lbl, val, _) in enumerate(scenarios):
    y = sy + i * inch(0.85)
    is_main = (i == 1)
    # 背景
    bg = COLOR["purple"] if is_main else COLOR["bg_alt"]
    tx = "FFFFFF" if is_main else COLOR["black"]
    sub_tx = COLOR["purple_lt"] if is_main else COLOR["muted"]
    fig.append(rect_shape(sp, f"sc_bg_{i}", right_x, y, right_w, inch(0.75), bg))
    sp += 1
    # ラベル
    fig.append(text_box(sp, f"sc_l_{i}", right_x + inch(0.25), y + inch(0.1),
                         right_w - inch(0.5), inch(0.22),
                         lbl, size=900, color=sub_tx, bold=True,
                         font=FONT_MONO, spacing=100))
    sp += 1
    # 値
    fig.append(text_box(sp, f"sc_v_{i}", right_x + inch(0.25), y + inch(0.32),
                         right_w - inch(0.5), inch(0.4),
                         val, size=2000, color=tx, bold=True,
                         font=FONT_MONO))
    sp += 1

# 下部: 所感バー
note_y = inch(4.9)
fig.append(text_box(sp, "note", inch(0.4), note_y, inch(9.2), inch(0.4),
                     "プレミアム（16h/月）は標準シナリオの約29%のみカバー。フェーズ別にカスタム月額プランへの切替を推奨。",
                     size=900, color=COLOR["dark"], italic=False, anchor_ctr=True))
sp += 1

replace_body_with_figure(SLIDES_DIR / "slide16.xml", "\n".join(fig))
print("slide16 done (retainer effort)")

# ============================================================
# slide17: プロジェクト型 工数積み上げ
# レイアウト: 3プロジェクトカード横並び + 合計
# ============================================================
set_content_header(SLIDES_DIR / "slide17.xml",
                    "CONTENT ／ 08", "08 / COST",
                    "プロジェクト型  工数積み上げ",
                    "PROJECT EFFORT", "14 / 18")

fig = []
sp = 100

left_x = inch(0.4)
body_y = inch(1.75)
full_w = inch(9.2)

fig.append(text_box(sp, "l_t", left_x, body_y, full_w, inch(0.3),
                     "3プロジェクトの工数・費用（標準シナリオ）",
                     size=1100, color=COLOR["black"], bold=True))
sp += 1
fig.append(h_line(sp, "l_ln", left_x, body_y + inch(0.38), full_w, COLOR["purple"], 19050))
sp += 1

# 3カード横並び
card_y = body_y + inch(0.6)
card_h = inch(2.2)
card_w = inch(2.96)
gap = inch(0.16)

projects = [
    ("A", "統合DB 構造設計", "＋ 共通マスタレビュー", "3〜4ヶ月", "244h", "¥2,440,000"),
    ("B", "生成AI 利用規程", "／ ガイドライン策定", "2〜3ヶ月", "123h", "¥1,230,000"),
    ("C", "AI推進担当者", "育成プログラム", "6ヶ月", "216h", "¥2,160,000"),
]
for i, (tag, name1, name2, period, hrs, cost) in enumerate(projects):
    cx = left_x + i * (card_w + gap)
    # カード本体 (紫)
    fig.append(rect_shape(sp, f"p_bg_{i}", cx, card_y, card_w, card_h, COLOR["purple"]))
    sp += 1
    # 左上の大タグ
    fig.append(text_box(sp, f"p_tag_{i}", cx + inch(0.25), card_y + inch(0.2),
                         inch(0.8), inch(0.8), tag,
                         size=4800, color=COLOR["purple_lt"], bold=True,
                         font="Georgia"))
    sp += 1
    # プロジェクト名 (2行)
    fig.append(text_box(sp, f"p_n1_{i}", cx + inch(0.25), card_y + inch(0.95),
                         card_w - inch(0.5), inch(0.3),
                         name1, size=1250, color="FFFFFF", bold=True))
    sp += 1
    fig.append(text_box(sp, f"p_n2_{i}", cx + inch(0.25), card_y + inch(1.25),
                         card_w - inch(0.5), inch(0.3),
                         name2, size=1050, color=COLOR["purple_lt"]))
    sp += 1
    # 区切り線
    fig.append(h_line(sp, f"p_s_{i}", cx + inch(0.25), card_y + inch(1.6),
                       card_w - inch(0.5), COLOR["purple_lt"], 6350))
    sp += 1
    # 期間・工数
    fig.append(text_box(sp, f"p_pe_{i}", cx + inch(0.25), card_y + inch(1.7),
                         card_w - inch(0.5), inch(0.2),
                         f"{period}  /  {hrs}", size=900, color=COLOR["purple_lt"],
                         font=FONT_MONO))
    sp += 1
    # 費用 (大)
    fig.append(text_box(sp, f"p_c_{i}", cx + inch(0.25), card_y + inch(1.92),
                         card_w - inch(0.5), inch(0.3),
                         cost, size=1500, color="FFFFFF", bold=True,
                         font=FONT_MONO))
    sp += 1

# 下部: 合計バー (濃紫で差別化)
total_y = card_y + card_h + inch(0.2)
fig.append(rect_shape(sp, "tot_bg", left_x, total_y, full_w, inch(0.55), COLOR["purple_dk"]))
sp += 1
fig.append(text_box(sp, "tot_l", left_x + inch(0.4), total_y, inch(4.0), inch(0.55),
                     "プロジェクト 3本 合計",
                     size=1100, color="FFFFFF", bold=True, anchor_ctr=True))
sp += 1
fig.append(text_box(sp, "tot_h", inch(5.5), total_y, inch(2.0), inch(0.55),
                     "583 h", size=1400, color="FFFFFF", bold=True,
                     anchor_ctr=True, font=FONT_MONO, align="r"))
sp += 1
fig.append(text_box(sp, "tot_v", inch(7.5), total_y, inch(2.0), inch(0.55),
                     "¥5,830,000", size=1700, color="FFFFFF", bold=True,
                     anchor_ctr=True, font=FONT_MONO, align="r"))
sp += 1

replace_body_with_figure(SLIDES_DIR / "slide17.xml", "\n".join(fig))
print("slide17 done (project cards)")

# ============================================================
# slide18: 12ヶ月トータル費用
# レイアウト: 左=月額顧問内訳 + プロジェクト型内訳の2段表
#             右=シナリオ別大きな金額
# ============================================================
set_content_header(SLIDES_DIR / "slide18.xml",
                    "CONTENT ／ 09", "09 / COST",
                    "12ヶ月トータル費用（標準シナリオ）",
                    "12M TOTAL", "15 / 18")

fig = []
sp = 100

left_x = inch(0.4)
body_y = inch(1.75)
left_w = inch(5.8)
right_x = inch(6.4)
right_w = inch(3.2)

# 左: 費用内訳
fig.append(text_box(sp, "l_t", left_x, body_y, left_w, inch(0.3),
                     "費用内訳",
                     size=1100, color=COLOR["black"], bold=True))
sp += 1
fig.append(h_line(sp, "l_ln", left_x, body_y + inch(0.38), left_w, COLOR["purple"], 19050))
sp += 1

# 月額顧問セクションヘッダ
sec_y = body_y + inch(0.55)
fig.append(rect_shape(sp, "m_sec_bg", left_x, sec_y, left_w, inch(0.3), COLOR["bg_alt"]))
sp += 1
fig.append(text_box(sp, "m_sec_l", left_x + inch(0.2), sec_y, inch(4.0), inch(0.3),
                     "月額顧問  （フェーズ別切替）",
                     size=900, color=COLOR["purple"], bold=True,
                     font=FONT_MONO, spacing=100, anchor_ctr=True))
sp += 1
fig.append(text_box(sp, "m_sec_v", left_x + inch(4.2), sec_y, inch(1.5), inch(0.3),
                     "¥6,000,000",
                     size=1000, color=COLOR["black"], bold=True,
                     font=FONT_MONO, align="r", anchor_ctr=True))
sp += 1

retainer_rows = [
    ("立ち上げ", "M1〜M3", "スタンダードカスタム", "¥1,680,000"),
    ("要件定義並走期", "M4〜M9", "スタンダードカスタム", "¥3,360,000"),
    ("運用移行期", "M10〜M12", "ライトカスタム", "¥960,000"),
]
for i, (phase, month, plan, cost) in enumerate(retainer_rows):
    y = sec_y + inch(0.35) + i * inch(0.32)
    fig.append(text_box(sp, f"rr_p_{i}", left_x + inch(0.2), y, inch(1.6), inch(0.3),
                         phase, size=900, color=COLOR["black"], anchor_ctr=True))
    sp += 1
    fig.append(text_box(sp, f"rr_m_{i}", left_x + inch(1.8), y, inch(0.9), inch(0.3),
                         month, size=850, color=COLOR["muted"], font=FONT_MONO,
                         anchor_ctr=True))
    sp += 1
    fig.append(text_box(sp, f"rr_n_{i}", left_x + inch(2.7), y, inch(1.7), inch(0.3),
                         plan, size=850, color=COLOR["dark"], anchor_ctr=True))
    sp += 1
    fig.append(text_box(sp, f"rr_c_{i}", left_x + inch(4.2), y, inch(1.5), inch(0.3),
                         cost, size=950, color=COLOR["black"], font=FONT_MONO,
                         align="r", anchor_ctr=True))
    sp += 1

# プロジェクト型セクション
sec2_y = sec_y + inch(1.4)
fig.append(rect_shape(sp, "p_sec_bg", left_x, sec2_y, left_w, inch(0.3), COLOR["bg_alt"]))
sp += 1
fig.append(text_box(sp, "p_sec_l", left_x + inch(0.2), sec2_y, inch(4.0), inch(0.3),
                     "プロジェクト型  （単発成果物）",
                     size=900, color=COLOR["purple"], bold=True,
                     font=FONT_MONO, spacing=100, anchor_ctr=True))
sp += 1
fig.append(text_box(sp, "p_sec_v", left_x + inch(4.2), sec2_y, inch(1.5), inch(0.3),
                     "¥5,830,000",
                     size=1000, color=COLOR["black"], bold=True,
                     font=FONT_MONO, align="r", anchor_ctr=True))
sp += 1

project_rows = [
    ("A", "統合DB設計 ＋ 共通マスタ", "¥2,440,000"),
    ("B", "生成AI利用ガイドライン", "¥1,230,000"),
    ("C", "AI推進担当者育成", "¥2,160,000"),
]
for i, (tag, name, cost) in enumerate(project_rows):
    y = sec2_y + inch(0.35) + i * inch(0.32)
    fig.append(rect_shape(sp, f"pt_t_{i}", left_x + inch(0.2), y + inch(0.05),
                           inch(0.3), inch(0.2), COLOR["amber"]))
    sp += 1
    fig.append(text_box(sp, f"pt_tx_{i}", left_x + inch(0.2), y + inch(0.05),
                         inch(0.3), inch(0.2), tag, size=800, color="FFFFFF",
                         bold=True, align="c", anchor_ctr=True, font=FONT_MONO))
    sp += 1
    fig.append(text_box(sp, f"pt_n_{i}", left_x + inch(0.6), y, inch(3.5), inch(0.3),
                         name, size=900, color=COLOR["black"], anchor_ctr=True))
    sp += 1
    fig.append(text_box(sp, f"pt_c_{i}", left_x + inch(4.2), y, inch(1.5), inch(0.3),
                         cost, size=950, color=COLOR["black"], font=FONT_MONO,
                         align="r", anchor_ctr=True))
    sp += 1

# 左下の太字合計 (位置を少し上げる)
grand_y = sec2_y + inch(1.35)
fig.append(rect_shape(sp, "gt_bg", left_x, grand_y, left_w, inch(0.55), COLOR["purple"]))
sp += 1
fig.append(text_box(sp, "gt_l", left_x + inch(0.2), grand_y, inch(3.0), inch(0.55),
                     "12ヶ月 トータル（標準）",
                     size=1000, color="FFFFFF", bold=True, anchor_ctr=True))
sp += 1
fig.append(text_box(sp, "gt_v", left_x + inch(3.5), grand_y, left_w - inch(3.7), inch(0.55),
                     "¥11,830,000", size=1900, color="FFFFFF", bold=True,
                     align="r", anchor_ctr=True, font=FONT_MONO))
sp += 1

# 右: シナリオ別3ピル縦並び
fig.append(text_box(sp, "r_t", right_x, body_y, right_w, inch(0.3),
                     "シナリオ別 レンジ",
                     size=1100, color=COLOR["black"], bold=True))
sp += 1
fig.append(h_line(sp, "r_ln", right_x, body_y + inch(0.38), right_w, COLOR["purple"], 19050))
sp += 1

scenes = [
    ("控えめ", "¥7,130,000", COLOR["bg_alt"], COLOR["black"], COLOR["muted"]),
    ("標準（推奨）", "¥11,830,000", COLOR["purple"], "FFFFFF", COLOR["purple_lt"]),
    ("手厚い", "¥17,420,000", COLOR["bg_alt"], COLOR["black"], COLOR["muted"]),
]
sy = body_y + inch(0.55)
for i, (lbl, val, bg, tx, sub) in enumerate(scenes):
    y = sy + i * inch(0.85)
    h_box = inch(0.72)
    fig.append(rect_shape(sp, f"sc_bg_{i}", right_x, y, right_w, h_box, bg))
    sp += 1
    fig.append(text_box(sp, f"sc_l_{i}", right_x + inch(0.2), y + inch(0.08),
                         right_w - inch(0.4), inch(0.22),
                         lbl, size=900, color=sub, bold=True,
                         font=FONT_MONO, spacing=100))
    sp += 1
    fig.append(text_box(sp, f"sc_v_{i}", right_x + inch(0.2), y + inch(0.3),
                         right_w - inch(0.4), inch(0.4),
                         val, size=1600, color=tx, bold=True, font=FONT_MONO))
    sp += 1

# 注記 (右カラム下に配置、2行)
note_y = inch(5.1)
fig.append(text_box_multi(sp, "note", right_x, note_y, right_w, inch(0.4),
    [("※ 月額顧問契約者にはプロジェクト費用の割引を適用。", {"size": 700, "color": COLOR["muted"]}),
     ("IT導入補助金・助成金の活用支援も対応します。", {"size": 700, "color": COLOR["muted"]})],
    line_space_pct=130000))
sp += 1

replace_body_with_figure(SLIDES_DIR / "slide18.xml", "\n".join(fig))
print("slide18 done (total cost)")

# ============================================================
# slide4: Next Steps (5ステップタイムライン)
# ============================================================
set_content_header(SLIDES_DIR / "slide4.xml",
                    "CONTENT ／ 10", "10 / NEXT",
                    "次のステップ",
                    "NEXT STEPS", "16 / 18")

fig = []
sp = 100

left_x = inch(0.4)
body_y = inch(1.75)
full_w = inch(9.2)

# 冒頭メッセージ
fig.append(text_box(sp, "intro", left_x, body_y, full_w, inch(0.35),
                     "本ご提案に基づき、以下のステップで支援開始までを進めさせていただければと考えております。",
                     size=1000, color=COLOR["dark"]))
sp += 1
fig.append(h_line(sp, "ln", left_x, body_y + inch(0.55), full_w, COLOR["border"]))
sp += 1

# 5ステップ (縦並びのタイムライン風)
steps = [
    ("01", "本提案書のご確認・論点共有", "オンラインMTG 60分  ／  論点・修正要望のすり合わせ"),
    ("02", "キックオフヒアリング", "各支援テーマの現状確認  ／  優先順位付け"),
    ("03", "詳細提案書のご提示", "スコープ・体制・金額確定版  ／  契約条件の調整"),
    ("04", "月額顧問契約の締結", "支援開始  ／  初回定例MTGのセッティング"),
    ("05", "プロジェクト型案件の順次着手", "月額顧問開始後のタイミング調整で順次スタート"),
]
step_y0 = body_y + inch(0.7)
step_h = inch(0.48)
gap = inch(0.04)
for i, (num, head, desc) in enumerate(steps):
    y = step_y0 + i * (step_h + gap)
    # 番号 (大きな紫ボックス)
    fig.append(rect_shape(sp, f"s_n_bg_{i}", left_x, y, inch(0.7), step_h, COLOR["purple"]))
    sp += 1
    fig.append(text_box(sp, f"s_n_{i}", left_x, y, inch(0.7), step_h,
                         num, size=1800, color="FFFFFF", bold=True,
                         align="c", anchor_ctr=True, font="Georgia"))
    sp += 1
    # 右側の内容ボックス
    content_x = left_x + inch(0.7)
    content_w = full_w - inch(0.7)
    fig.append(rect_shape(sp, f"s_c_bg_{i}", content_x, y, content_w, step_h, COLOR["bg_alt"]))
    sp += 1
    # ヘッディング
    fig.append(text_box(sp, f"s_h_{i}", content_x + inch(0.3), y + inch(0.06),
                         content_w - inch(0.3), inch(0.22),
                         head, size=1050, color=COLOR["black"], bold=True))
    sp += 1
    # 説明
    fig.append(text_box(sp, f"s_d_{i}", content_x + inch(0.3), y + inch(0.26),
                         content_w - inch(0.3), inch(0.2),
                         desc, size=850, color=COLOR["dark"]))
    sp += 1

# フッター注記 (最終ステップの下に余裕を持たせて配置)
note_y = step_y0 + 5 * (step_h + gap) + inch(0.1)
fig.append(text_box(sp, "note", left_x, note_y, full_w, inch(0.3),
                     "— ご質問・論点のご指摘はいつでもお気軽にお申し付けください。",
                     size=900, color=COLOR["purple"], italic=True))
sp += 1

replace_body_with_figure(SLIDES_DIR / "slide4.xml", "\n".join(fig))
print("slide4 (Next Steps) done")

# ============================================================
# slide5, slide6 (そのまま)
# ============================================================
replace_text(SLIDES_DIR / "slide5.xml", [
    ("YYYY年MM月", "2024年10月"),
    ("<a:t>05 / 06</a:t>", "<a:t>17 / 18</a:t>"),
])
print("slide5 done")

replace_text(SLIDES_DIR / "slide6.xml", [
    ("<a:t>06 / 06</a:t>", "<a:t>18 / 18</a:t>"),
])
print("slide6 done")

print("\n=== Part 4 done (All slides complete) ===")
