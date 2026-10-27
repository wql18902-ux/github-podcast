#!/usr/bin/env python3
"""下一期期号：max(ep<N>- 目录名) + 1。**不是 episodes.log 行数。**

为什么另写一个、不 import agent.state.next_ep_no：
手动链路（pipeline.sh / ab-denoise.sh）不该被 agent 的库锁或坏库拖累——
所以这里刻意零依赖：纯 stdlib、只扫目录名、不连 SQLite、不产生任何 .db。
两边同口径（那边多取 DB 里的 max），一致性由 tests/test_ep_next_no.py 锁死。

用法：
    python3 scripts/ep_no.py                  # 默认扫 output/episodes/
    python3 scripts/ep_no.py <episodes目录>     # 指定目录（测试与排查用）

wc -l 当期号错过两次：2026-09-21 是 37 行对期号 15（agent/state.py docstring 记着），
2026-10-04 是 63 行对 23 期。log 一行一个**仓库**（还有 `topic:` 回馈和 `#` 注释行），
从来不是期号。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 跟 agent/state.py:154 同一条正则：目录名 ep<数字>-<slug>。
EP_DIR_RE = re.compile(r"^ep(\d+)-")


def next_no(episodes_dir: Path) -> int:
    """episodes 目录下最大期号 + 1；目录不存在或没有合规目录名 → 1。"""
    if not episodes_dir.is_dir():
        return 1
    top = 0
    for child in episodes_dir.iterdir():
        m = EP_DIR_RE.match(child.name)
        if m:
            top = max(top, int(m.group(1)))
    return top + 1


def main(argv: list[str]) -> int:
    episodes_dir = Path(argv[1]) if len(argv) > 1 else Path("output/episodes")
    print(next_no(episodes_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
