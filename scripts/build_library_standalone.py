#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 web/library 打成一个单文件 HTML（CSS/JS/数据全内联），
方便直接丢进 WorkBuddy 或任何只收一个 HTML 的托管。
音频改成绝对地址，默认指向 GitHub Pages 上的同一份文件。"""
import re
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "web" / "library"
OUT = LIB / "dist" / "页声-判断库-单文件.html"
AUDIO_BASE = "https://wql18902-ux.github.io/sourcecast/media/"


def main():
    html = (LIB / "index.html").read_text(encoding="utf-8")
    for ref in ('styles.css','studio.css'):
        html=html.replace(f'<link rel="stylesheet" href="{ref}">', '<style>\n'+(LIB/ref).read_text()+'\n</style>')
    for ref in ('data.js','data/styles.js','data/cloud.js','vendor/cloud-sdk.js','app.js','studio.js'):
        text=(LIB/ref).read_text().replace('`media/ep${ep.no}-preview.m4a`',f'`{AUDIO_BASE}ep${{ep.no}}-preview.m4a`').replace('src="media/ep${ep.no}-preview.m4a"',f'src="{AUDIO_BASE}ep${{ep.no}}-preview.m4a"')
        text=text.replace('</script', '<\\/script')
        html=html.replace(f'<script src="{ref}"></script>', '<script>\n'+text+'\n</script>')
    html=html.replace('href="sourcecast-source.zip"', 'href="https://wql18902-ux.github.io/sourcecast/sourcecast-source.zip"')

    assert '<link rel="stylesheet"' not in html, "CSS 没内联成功"
    assert "<script src=" not in html, "JS 没内联成功"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    sys.exit(main())
