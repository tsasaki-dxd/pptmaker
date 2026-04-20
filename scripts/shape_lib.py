#!/usr/bin/env python3
"""
テンプレートに図・表を埋め込むためのXMLフラグメント生成ライブラリ
座標単位: EMU (1インチ=914400 EMU)。スライドは9144000×5143500 EMU (10×5.625in)
"""

# カラーパレット (柔らかいトーン / 色味控えめ)
COLOR = {
    "purple":    "8B7AB8",   # メイン紫 (淡いラベンダー寄り)
    "purple_lt": "D9D1E8",   # 淡い紫
    "purple_bg": "F5F2F9",   # 極淡紫背景
    "purple_dk": "6B5C96",   # 濃紫 (合計バー等の差別化用、控えめ)
    "black":     "3A3A42",   # 濃グレー (文字色)
    "dark":      "5E5C6A",   # サブテキスト
    "muted":     "9B98A6",   # ミュート
    "border":    "E8E6EC",   # 罫線
    "bg_alt":    "FAFAFB",   # カード背景
    "amber":     "C4A05C",   # プロジェクト型 (くすんだゴールド)
    "green":     "5E9B7F",   # 月額顧問 (くすんだセージグリーン)
    "white":     "FFFFFF",
    "accent_bg": "F0EBF7",   # 強調用の薄紫背景
}

FONT_JP = "Noto Sans JP"
FONT_MONO = "Consolas"

def inch(v):
    """インチ→EMU"""
    return int(v * 914400)

def pt(v):
    """ポイントは100倍して格納(pptxの慣習)"""
    return int(v * 100)


def _i(v):
    """EMU値を必ず整数化（PowerPoint互換性）"""
    return int(round(v))


def rect_shape(sp_id, name, x, y, w, h, fill_color, line_color=None, line_w=0):
    """単純な塗りつぶし長方形"""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    line_xml = ""
    if line_color:
        line_xml = f'''<a:ln w="{line_w}"><a:solidFill><a:srgbClr val="{line_color}"/></a:solidFill></a:ln>'''
    else:
        line_xml = "<a:ln/>"
    return f'''<p:sp>
<p:nvSpPr><p:cNvPr id="{sp_id}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
<a:solidFill><a:srgbClr val="{fill_color}"/></a:solidFill>
{line_xml}
</p:spPr>
</p:sp>'''


def rect_outline(sp_id, name, x, y, w, h, line_color, line_w=6350):
    """塗りなし罫線付き長方形"""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    return f'''<p:sp>
<p:nvSpPr><p:cNvPr id="{sp_id}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
<a:noFill/>
<a:ln w="{line_w}"><a:solidFill><a:srgbClr val="{line_color}"/></a:solidFill></a:ln>
</p:spPr>
</p:sp>'''


def text_box(sp_id, name, x, y, w, h, text, *,
             size=1100, color="111014", bold=False, italic=False,
             font=FONT_JP, align="l", valign="t",
             spacing=0, anchor_ctr=False):
    """単一行テキストボックス。textはXMLエスケープ済みを想定"""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    b_attr = ' b="1"' if bold else ""
    i_attr = ' i="1"' if italic else ""
    spc = f' spc="{spacing}" kern="0"' if spacing else ""
    anchor = ' anchor="ctr"' if anchor_ctr else ""
    align_attr = ""
    if align == "c":
        align_attr = ' algn="ctr"'
    elif align == "r":
        align_attr = ' algn="r"'
    return f'''<p:sp>
<p:nvSpPr><p:cNvPr id="{sp_id}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
<a:noFill/><a:ln/></p:spPr>
<p:txBody>
<a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" rtlCol="0"{anchor}/>
<a:lstStyle/>
<a:p><a:pPr{align_attr} indent="0" marL="0"><a:buNone/></a:pPr>
<a:r><a:rPr lang="ja-JP" sz="{size}"{b_attr}{i_attr}{spc} dirty="0">
<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
<a:latin typeface="{font}"/><a:ea typeface="{font}"/><a:cs typeface="{font}"/>
</a:rPr><a:t>{text}</a:t></a:r>
</a:p></p:txBody>
</p:sp>'''


def text_box_multi(sp_id, name, x, y, w, h, lines, *,
                   size=1000, color="111014", font=FONT_JP, align="l",
                   line_space_pct=None):
    """複数行テキスト。lines=[(text, {size,bold,color,spc}), ...]"""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    align_attr = ""
    if align == "c":
        align_attr = ' algn="ctr"'
    elif align == "r":
        align_attr = ' algn="r"'
    ln_spc = ""
    if line_space_pct:
        ln_spc = f'<a:lnSpc><a:spcPct val="{line_space_pct}"/></a:lnSpc>'
    paragraphs = []
    for item in lines:
        if isinstance(item, tuple):
            txt, opts = item
        else:
            txt, opts = item, {}
        sz = opts.get("size", size)
        clr = opts.get("color", color)
        bold = ' b="1"' if opts.get("bold") else ""
        fnt = opts.get("font", font)
        spc = f' spc="{opts["spc"]}" kern="0"' if opts.get("spc") else ""
        paragraphs.append(f'''<a:p><a:pPr{align_attr} indent="0" marL="0">{ln_spc}<a:buNone/></a:pPr>
<a:r><a:rPr lang="ja-JP" sz="{sz}"{bold}{spc} dirty="0">
<a:solidFill><a:srgbClr val="{clr}"/></a:solidFill>
<a:latin typeface="{fnt}"/><a:ea typeface="{fnt}"/><a:cs typeface="{fnt}"/>
</a:rPr><a:t>{txt}</a:t></a:r></a:p>''')
    body = "\n".join(paragraphs)
    return f'''<p:sp>
<p:nvSpPr><p:cNvPr id="{sp_id}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
<a:noFill/><a:ln/></p:spPr>
<p:txBody><a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" rtlCol="0"/>
<a:lstStyle/>
{body}
</p:txBody>
</p:sp>'''


def pill_label(sp_id, name, x, y, w, h, text, *,
               bg_color, text_color="FFFFFF", size=900, bold=True, spacing=200):
    """色付きピル(ラベル)。幅と高さを与えて塗り長方形+中央テキスト"""
    x, y, w, h = _i(x), _i(y), _i(w), _i(h)
    # 長方形 + テキスト (2要素返す)
    bg_id = sp_id
    tx_id = sp_id + 1
    b = ' b="1"' if bold else ""
    spc = f' spc="{spacing}" kern="0"' if spacing else ""
    shape = rect_shape(bg_id, f"{name}_bg", x, y, w, h, bg_color)
    text = f'''<p:sp>
<p:nvSpPr><p:cNvPr id="{tx_id}" name="{name}_tx"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
<a:noFill/><a:ln/></p:spPr>
<p:txBody><a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" rtlCol="0" anchor="ctr"/>
<a:lstStyle/>
<a:p><a:pPr algn="ctr" indent="0" marL="0"><a:buNone/></a:pPr>
<a:r><a:rPr lang="en-US" sz="{size}"{b}{spc} dirty="0">
<a:solidFill><a:srgbClr val="{text_color}"/></a:solidFill>
<a:latin typeface="{FONT_JP}"/><a:ea typeface="{FONT_JP}"/><a:cs typeface="{FONT_JP}"/>
</a:rPr><a:t>{text}</a:t></a:r></a:p></p:txBody>
</p:sp>'''
    return shape + "\n" + text


def h_line(sp_id, name, x, y, w, color=COLOR["border"], width=6350):
    """水平線"""
    x, y, w = _i(x), _i(y), _i(w)
    return f'''<p:sp>
<p:nvSpPr><p:cNvPr id="{sp_id}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="0"/></a:xfrm>
<a:prstGeom prst="line"><a:avLst/></a:prstGeom>
<a:noFill/>
<a:ln w="{width}"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:prstDash val="solid"/></a:ln>
</p:spPr>
</p:sp>'''
