#!/usr/bin/env python3
"""读听众画像，给各处 prompt 用。

「讲给谁听、他的现实约束是什么」只有一份真相源：`config/audience.md`。
选稿 prompt、写稿 prompt、审稿 prompt 全都从这里取，不要在哪一份里写死个人信息——
写死了就是「换听众要改八个地方」，而且总有一个地方忘了改。

用法：
    import audience
    brief = audience.brief()      # 一段可直接插进 prompt 的听众摘要
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIENCE_FILE = PROJECT_ROOT / "config" / "audience.md"
AUDIENCE_EXAMPLE = PROJECT_ROOT / "config" / "audience.example.md"


def _sections(text: str) -> dict[str, str]:
    """按 `## 标题` 切文件。切不完就整篇当一节。"""
    parts = re.split(r"^##\s+", text, flags=re.M)
    out: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        out[parts[i].strip()] = parts[i + 1] if i + 1 < len(parts) else ""
    return out


def raw() -> str:
    """整份画像原文。读不到返回空串（缺画像不该让选稿脚本崩）。"""
    if not AUDIENCE_FILE.is_file():
        return ""
    return AUDIENCE_FILE.read_text(encoding="utf-8", errors="replace")


def profile_section() -> str:
    """只取「我的画像」那一节——「怎么写」和「示例」不该进 prompt。"""
    text = raw()
    if not text:
        return ""
    for key, body in _sections(text).items():
        if "画像" in key:
            return body.strip()
    return ""


def brief() -> str:
    """给 prompt 用的一段听众摘要。

    没有 config/audience.md（刚 clone 下来、还没 cp 模板）时，返回一句明确提示，
    让调用方 prompt 退化到「写给一个具体的普通读者」，而不是静悄悄地按某个不存在的人写。
    """
    sec = profile_section()
    if sec:
        return sec
    hint = ""
    if AUDIENCE_EXAMPLE.is_file():
        hint = "模板在 config/audience.example.md，先 `cp config/audience.example.md config/audience.md` 再填。"
    return f"（听众画像未填。{hint}按「一个具体的、非专业程序员的读者」写，不要涉及他的私事。）"
