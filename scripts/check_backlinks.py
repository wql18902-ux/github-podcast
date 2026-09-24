#!/usr/bin/env python3
"""双链校验：扫项目里所有 md 的 [[...]] 双链，检查目标是否都真实存在。

规则（见项目 AGENTS.md「双链写法」）：
  - [[ep<N>-<slug>]]  → output/episodes/ep<N>-<slug>/page.md 必须存在（目录 + page.md）
  - [[agent-map]]      → 项目根 agent-map.md 必须存在
  - [[文件名]]         → 全项目里存在同名 .md 文件（basename 匹配）
只读，不改任何文件。悬空链接 > 0 时退出码 1（让调用方看得见）。

跑法：python3 scripts/check_backlinks.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK_PAT = re.compile(r"\[\[([^\[\]]+?)\]\]")

# 扫描范围：项目里的 md（跳过 cache / output/audio / _归档 / 隐藏目录）
SKIP_PARTS = {"cache", "audio", "_归档", "__pycache__", ".git"}
SKIP_NAMES = {"latest-script.md"}  # 大稿子也扫，但这条留着防止误伤（当前不禁）


def iter_md_files():
    for p in ROOT.rglob("*.md"):
        rel = p.relative_to(ROOT)
        if any(part in SKIP_PARTS or part.startswith(".") for part in rel.parts):
            continue
        yield p, rel


def build_target_set():
    """所有可作为双链目标的实体。"""
    targets = set()
    # 1) 期次页：目录名（ep3-hermes-agent）
    ep_dir = ROOT / "output" / "episodes"
    if ep_dir.is_dir():
        for d in ep_dir.iterdir():
            if d.is_dir() and (d / "page.md").exists():
                targets.add(d.name)
    # 2) 任意 md 的 basename（去掉 .md），供 [[文件名]] 用
    for p, _ in iter_md_files():
        targets.add(p.stem)
    return targets


def main():
    targets = build_target_set()
    dangling = []
    total = 0
    for path, rel in iter_md_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), 1):
            for m in LINK_PAT.finditer(line):
                raw = m.group(1).strip()
                # 拆掉可能的显示别名 [[target|显示名]]
                target = raw.split("|")[0].strip()
                # 跳过语法示例里的占位符（含 <> 的模板写法，不是真链接）
                if "<" in target or ">" in target:
                    continue
                total += 1
                if target not in targets:
                    dangling.append((str(rel), line_no, raw))

    print(f"[.] 扫描 {len(list(iter_md_files()))} 个 md，共 {total} 条双链")
    print(f"[.] 可解析目标 {len(targets)} 个（期次目录 + md 文件名）")
    if dangling:
        print(f"[✗] 悬空双链 {len(dangling)} 条：")
        for rel, ln, raw in dangling:
            print(f"    {rel}:{ln}  [[{raw}]]")
        sys.exit(1)
    print("[✓] 无悬空双链")


if __name__ == "__main__":
    main()
