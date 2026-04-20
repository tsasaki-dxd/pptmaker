#!/usr/bin/env python3
"""
テンプレ元の全スライドに対して:
1. Yu Gothic → Noto Sans JP へ置換
2. 111014 (濃い黒) → 3A3A42 (濃グレー) へ置換
3. 6D28D9 (濃紫) → 8B7AB8 (淡紫) へ置換
4. 8B8794 (ミュート) → 9B98A6 へ置換
5. 3A3742 (dark) → 5E5C6A へ置換
"""
from pathlib import Path

SLIDES_DIR = Path("/home/claude/template_unpacked/ppt/slides")

# 大文字小文字両方を考慮した置換マップ
REPLACE = [
    ('typeface="Yu Gothic"', 'typeface="Noto Sans JP"'),
    # テキスト色・背景色としての色
    ("111014", "3A3A42"),   # 黒 → 濃グレー
    ("6D28D9", "8B7AB8"),   # 濃紫 → 柔らかい紫
    ("8B8794", "9B98A6"),   # ミュートグレー調整
    ("3A3742", "5E5C6A"),   # サブテキスト調整
]

for p in sorted(SLIDES_DIR.glob("slide*.xml")):
    content = p.read_text(encoding="utf-8")
    orig = content
    for old, new in REPLACE:
        content = content.replace(old, new)
    if content != orig:
        p.write_text(content, encoding="utf-8")
        print(f"{p.name}: normalized")
    else:
        print(f"{p.name}: no change")
