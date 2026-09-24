#!/usr/bin/env python3
"""项目路径解析。

外环所有脚本都用这里的函数拿路径，别各自写 `Path(__file__).parent.parent`——
那种写法在 launchd / cron / 不同 cwd 下最容易出的错就是「算出来是别处」。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os

# agent/paths.py → agent/ → 项目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIR = PROJECT_ROOT / "config"
OUTPUT_DIR = PROJECT_ROOT / "output"
SCRIPT_DIR = PROJECT_ROOT / "scripts"
AUDIO_DIR = OUTPUT_DIR / "audio"
EPISODES_DIR = OUTPUT_DIR / "episodes"

# 与豆包那班的两个契约文件（§1.1：格式一字不改）
LATEST_SCRIPT = OUTPUT_DIR / "latest-script.md"
LATEST_STATUS = OUTPUT_DIR / "latest-status.txt"

# 外环 ↔ 内环的文件契约
REQUEST_JSON = PROJECT_ROOT / "agent" / "request.json"
DONE_JSON = PROJECT_ROOT / "agent" / "done.json"

EPISODES_LOG = OUTPUT_DIR / "episodes.log"
# 库路径允许用环境变量顶掉——排障与干跑（agent.cli --dry-run）要能在临时库上跑，
# 不然试一次就污染当期的真实状态。
DB_PATH = Path(os.environ.get("PODCAST_AGENT_DB") or (PROJECT_ROOT / "info_source.db"))


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """读 config/agent.json。配置是唯一的口径真相源，所以这里不做任何默认值兜底——
    键写错了要当场炸，不要静默用默认值跑（那正是「三处口径对不上」的来源）。"""
    p = Path(path) if path else CONFIG_DIR / "agent.json"
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def rel(path: str | Path) -> str:
    """转成相对项目根的路径（写进 DB / request.json 用这个，日志里给人看也这个）。"""
    p = Path(path)
    try:
        return str(p.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


def abs_path(path: str | Path) -> Path:
    """相对项目根的路径 → 绝对路径。"""
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def date_paths(date: str) -> dict[str, Path]:
    """一期在「当期路径」上的几个固定位置。注意这些都是**每晚被盖写**的路径，
    归档件在 output/episodes/ep<N>-<slug>/ 下（见 docs，别混）。"""
    return {
        "script_dated": OUTPUT_DIR / f"{date}-script.md",
        "breakdown": OUTPUT_DIR / f"{date}-breakdown.md",
        "review": OUTPUT_DIR / f"{date}-review.md",
        "brief": OUTPUT_DIR / f"{date}-brief.md",
    }


def read_daily_brief(date: str) -> str:
    """当日清单摘要（fetch.py 写的 output/<日期>.md），给 request.json 的 brief 用。
    读不到就返回空串——brief 缺了不该拦整期。"""
    p = OUTPUT_DIR / f"{date}.md"
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    return text[:4000]
