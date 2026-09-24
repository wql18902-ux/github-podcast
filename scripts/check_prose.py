#!/usr/bin/env python3
"""中文成稿质检：只报警，不自动改文。

本项目自带的最小版检查器。判据全部来自本项目自己的红线（见 README「文稿口径」、
docs/讲人话规则），不依赖任何外部 skill。要更全的检查，自己换一个脚本，
把路径写进环境变量 PROSE_CHECKER 即可（见文末）。

用法：
    python3 scripts/check_prose.py <稿子.md> [--all] [--punct]

默认只报「硬禁」类——命中就必须改。加 --all 连「建议改」类一起报。

**标点默认不报。** 本项目口径明确忽略破折号和冒号（口播稿里它们是断句工具，
不是文风毛病），所以 FORBIDDEN_PUNCTUATION 那一类要显式加 --punct 才查。
拿不准一份稿子的时候，两个开关一起给：--all --punct。

退出码：0 = 无硬禁命中；1 = 有硬禁命中；2 = 用法/读取错误。

这是**最小版**检查器，只覆盖本项目自己声明的红线（硬禁词 / 黑话 / 翻案句 /
文艺腔 / 路标句 / 名词化 / 语气词密度）。它不判同构排比、长前置成分、重定语句——
那几类要更重的分析。想换更全的检查器，把路径写进环境变量 PROSE_CHECKER，本脚本会转交。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ── 硬禁：命中就必须改 ──────────────────────────────────────────────
HARD_STOPS = (
    "说白了",
    "说穿了",
    "先说结论",
)

HARD_JARGON = (
    "赋能", "抓手", "商业闭环", "价值闭环", "能力沉淀", "拉通",
    "底层逻辑", "顶层设计", "认知跃迁", "价值释放", "降本增效",
    "内容矩阵", "全链路", "组合拳", "打开想象空间", "结构性机会",
    "关键命题", "深层逻辑", "技术底座", "公共底座", "技术主权",
    "认知增量", "迭代闭环",
)

# 翻案句：「不是 A 而是 B」及其一整族变体。本项目口径是禁的——
# 结论直接说，不用先立一个假的再推翻。
PIVOT_PATTERNS = (
    re.compile(r"(?:并)?不是[^。！？\n]{0,90}而是"),
    re.compile(r"并非[^。！？\n]{0,90}而是"),
    re.compile(r"不在于[^。！？\n]{0,90}而在于"),
    re.compile(r"与其说[^。！？\n]{0,90}(?:不如|毋宁|倒不如)"),
    re.compile(r"表面(?:上)?[^。！？\n]{0,90}(?:其实|实际|实则)"),
    re.compile(r"看似[^。！？\n]{0,90}(?:其实|实际|实则)"),
    re.compile(r"真正[^，。！？\n]{0,16}的[，]?是"),
)

FORBIDDEN_PUNCTUATION = {
    "：": "中文冒号",
    ":": "英文冒号",
    "—": "破折号",
    "–": "连接号式破折号",
}

# ── 建议改：不拦，但列出来给人看一眼 ────────────────────────────────
CONTEXT_JARGON = (
    "沉淀", "颗粒度", "对齐", "协同", "链路", "生态位",
    "心智", "范式", "方法论", "核心变量", "打法", "闭环",
)

LYRIC_WORDS = (
    "安放", "抵达", "微光", "褶皱", "丰盈", "滚烫",
    "轻盈", "赤裸", "剥开",
)

ROAD_SIGNS = (
    "更微妙的是", "还有一层", "只说对了一半", "值得注意的是",
    "需要指出的是", "从某种意义上说",
)

NOMINALIZATION_PATTERNS = (
    re.compile(r"进行(?:了|一次|一场|着)?[^。，！？\n]{0,10}(?:调整|优化|升级|分析|讨论|沟通|梳理|复盘|迭代|探索|尝试|思考|规划|布局)"),
    re.compile(r"起到了?[^。！？\n]{0,12}的?作用"),
    re.compile(r"具有[^。！？\n]{0,10}(?:意义|价值)"),
)


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _hits(line: str, needles: tuple[str, ...] | list[str]) -> list[str]:
    return [w for w in needles if w in line]


def check(text: str, show_all: bool, show_punct: bool) -> tuple[list[str], list[str]]:
    """返回 (硬禁命中, 建议命中)。每条都带行号。"""
    hard: list[str] = []
    soft: list[str] = []
    lines = _lines(text)

    for n, line in enumerate(lines, 1):
        # 代码块 / 引用块里的话是素材不是成稿，跳过
        stripped = line.lstrip()
        if stripped.startswith(("```", "|", ">", "#")):
            continue

        for w in _hits(line, HARD_STOPS):
            hard.append(f"L{n} 硬禁词「{w}」")
        for w in _hits(line, HARD_JARGON):
            hard.append(f"L{n} 黑话「{w}」")

        for pat in PIVOT_PATTERNS:
            m = pat.search(line)
            if m:
                hard.append(f"L{n} 翻案句「{m.group(0)[:40]}」")

        if show_punct:
            for ch, name in FORBIDDEN_PUNCTUATION.items():
                if ch in line:
                    soft.append(f"L{n} {name}（本项目口径默认忽略，--punct 才查）")

        if not show_all:
            continue

        for w in _hits(line, CONTEXT_JARGON):
            soft.append(f"L{n} 待定黑话「{w}」")
        for w in _hits(line, LYRIC_WORDS):
            soft.append(f"L{n} 文艺腔「{w}」")
        for w in _hits(line, ROAD_SIGNS):
            soft.append(f"L{n} 路标句「{w}」")
        for pat in NOMINALIZATION_PATTERNS:
            m = pat.search(line)
            if m:
                soft.append(f"L{n} 名词化「{m.group(0)[:30]}」")

    # 语气词密度：每千字 ≤3（口播稿的硬口径，超了听着就腻）。
    # 短稿不判——几百字的片段里出现一个「然后」是正常行文，不是毛病。
    han = len(re.findall(r"[一-鿿]", text))
    if han >= 500:
        for word in ("然后", "其实", "就是", "对吧"):
            c = text.count(word)
            if c / han * 1000 > 3:
                soft.append(f"全文 语气词「{word}」密度 {c}/{han} 字 = 每千字 {c / han * 1000:.1f} 个（闸 3）")

    return hard, soft


def main() -> int:
    ap = argparse.ArgumentParser(description="中文成稿质检：只报警，不自动改文")
    ap.add_argument("path", help="稿子路径（.md / .txt）")
    ap.add_argument("--all", action="store_true", help="连「建议改」类一起报")
    ap.add_argument(
        "--punct",
        action="store_true",
        help="也报冒号/破折号。本项目口径默认忽略这两类，所以默认不查",
    )
    args = ap.parse_args()

    p = Path(args.path)
    if not p.is_file():
        print(f"[!] 读不到文件：{p}", file=sys.stderr)
        return 2
    text = p.read_text(encoding="utf-8", errors="replace")

    hard, soft = check(text, args.all, args.punct)

    if hard:
        print(f"[✗] {len(hard)} 处硬禁命中（{p}）：")
        for h in hard:
            print(f"    {h}")
    if soft:
        print(f"[!] {len(soft)} 处建议改（{p}）：")
        for s in soft:
            print(f"    {s}")
    if not hard and not soft:
        print(f"[OK] {p} 干净")

    # 想换成更全的检查器：设 PROSE_CHECKER=<你的脚本>，本脚本会转交后以其退出码为准。
    import os
    import subprocess
    alt = os.environ.get("PROSE_CHECKER")
    if alt:
        rc = subprocess.run([alt, str(p)]).returncode
        return rc
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
