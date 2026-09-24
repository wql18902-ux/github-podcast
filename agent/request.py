#!/usr/bin/env python3
"""外环 ↔ 内环的文件契约（设计稿 §4.1 结尾 / §6.4）。

外环**不「调用」宿主**，而是通过文件请求：写 agent/request.json，宿主会话读它、
干完落盘产物、写 agent/done.json。外环只看 done.json 与产物 mtime，
不关心会话内部发生了什么——跟豆包那班同一套松耦合思路，已验证有效。

为什么不做成「外环启动宿主 CLI」：
  - 那要求外环认识每家的命令行，等于把宿主编译进编排层，换宿主就得改编排；
  - WorkBuddy 的自动化本来就是从宿主侧唤醒的，外环是被唤醒的一方，不是发起方。
文件契约让「谁先谁后」变得不重要：谁先跑都行，谁后跑看文件。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from . import paths, state

TASKS = ("draft", "review")


def _scheduled_selection(date: str) -> dict[str, Any]:
    """今天排期上的选题（选题库第 4 块的来源）。

    **只读**，而且读不到就返回空——不能因为工作台没开、飞书没同步就让整期起不来。
    直接查库而不是 import scripts/selection_db.py：少一层耦合，且本模块只读不写。
    """
    if not paths.DB_PATH.exists():
        return {}
    try:
        con = sqlite3.connect(f"file:{paths.DB_PATH}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "select id, title, project, url, summary, status from selections"
                " where scheduled_for = ? order by id desc limit 1",
                (date,),
            ).fetchall()
            return dict(rows[0]) if rows else {}
        finally:
            con.close()
    except sqlite3.Error:
        return {}


def build_brief(date: str, repos: list[str], cfg: dict[str, Any]) -> str:
    """当日清单摘要 + 为什么选这些 + 拼盘要求。宿主会话第一屏看的就是它。"""
    parts: list[str] = []
    daily = paths.read_daily_brief(date)
    if daily:
        parts.append("## 当日清单摘要\n\n" + daily)

    sel = _scheduled_selection(date)
    if sel:
        parts.append(
            "## 今天排期上写的选题（人工预选，优先照它；要换得说清为什么）\n\n"
            f"- 标题：{sel.get('title') or '（空）'}\n"
            f"- 项目：{sel.get('project') or '（空）'}\n"
            f"- 链接：{sel.get('url') or '（空）'}\n"
            f"- 说明：{sel.get('summary') or '（空）'}\n"
        )

    max_n = cfg["budget"]["max_projects_per_episode"]
    repo_lines = "\n".join(f"- {r}" for r in repos) or "-（选料没产出新仓，按当周主题自选）"
    parts.append(
        "## 本期仓库\n\n"
        f"{repo_lines}\n\n"
        f"## 拼盘要求\n\n"
        f"- 一期最多 {max_n} 个仓库，每个都要走完拆解 10 字段，**不许只讲一个就收**\n"
        f"- 体量口径：正文 ≥{cfg['gates']['length']['min_chars']} 汉字（≈51 分钟）；"
        f"单项目只够 3600-4025 汉字（≈24 分钟），撑不起就拼盘\n"
        f"- 读源码至少要碰 {cfg['budget']['min_files_read']} 个文件（回执里要报 files_read）\n"
    )
    if sel.get("project") and not any(sel.get("project") in r for r in repos):
        parts.append(
            f"\n> 注意：排期写的是 `{sel['project']}`，但选料脚本产出的是上面的仓。"
            f"两边不一致时**以排期为准**，并在回执 notes 里写清为什么改了。\n"
        )
    return "\n".join(parts)


def write_request(
    date: str,
    *,
    ep_no: int,
    task: str = "draft",
    repos: list[str] | None = None,
    cfg: dict[str, Any],
    brief: str | None = None,
    inputs: dict[str, str] | None = None,
    path: str | Path | None = None,
) -> str:
    """写 agent/request.json，返回路径。task 区分这一轮是写稿还是审稿。"""
    if task not in TASKS:
        raise ValueError(f"task 只能是 {TASKS}，收到 {task!r}")

    p = Path(path) if path else paths.REQUEST_JSON
    common = {
        "date": date,
        "ep_no": ep_no,
        "task": task,
        "require": {
            "prompt": "scripts/write-episode-prompt.md",
            "skill": "podcast-depth-writing",
            "model": cfg["models"]["drafting"],
            "min_files_read": cfg["budget"]["min_files_read"],
        },
    }

    if task == "draft":
        repos = list(repos or [])
        common["repos"] = repos
        common["brief"] = brief if brief is not None else build_brief(date, repos, cfg)
        common["outputs"] = {
            "script": "output/latest-script.md",
            "script_dated": f"output/{date}-script.md",
            "breakdown": f"output/{date}-breakdown.md",
        }
    else:
        dp = paths.date_paths(date)
        prev = state.previous_episode_script(date)
        common["inputs"] = {
            "script": "output/latest-script.md",
            "breakdown": paths.rel(dp["breakdown"]),
            "prev_script": prev or "",
            "episodes_log": "output/episodes.log",
            "news_ledger": "output/news-covered.md",
        }
        common["require"].update(
            {
                "mode": "review-only",
                # 冗余但必要的双保险：prompt 里已禁重写，这里再声明一次（§6.4）
                "allow_rewrite": cfg["review"]["allow_rewrite"],
                "checks": cfg["review"]["checks"],
                "trigger_severity": cfg["review"]["trigger_severity"],
            }
        )
        common["outputs"] = {"review": paths.rel(dp["review"])}
        if inputs:
            common["inputs"].update(inputs)

    common["request_id"] = hashlib.sha1(
        json.dumps(common, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    common["written_at"] = state.now()

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(common, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def read_request(path: str | Path | None = None) -> dict[str, Any] | None:
    p = Path(path) if path else paths.REQUEST_JSON
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def read_done(
    date: str,
    task: str = "draft",
    *,
    path: str | Path | None = None,
    request_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """读 agent/done.json。三种情况都返回 None（= 会话还没干完）：

      1. done.json 不存在；
      2. date / task 对不上（是别的轮次留下的回执）；
      3. done.json 比 request.json 旧——**这条最关键**：上一轮的回执还在，
         外环重入时会把它当成「这一轮干完了」，于是跳过写稿直接进 verify，
         拿旧稿当新稿验。加 mtime 比较就是为了堵这个。
    """
    p = Path(path) if path else paths.DONE_JSON
    if not p.exists():
        return None
    try:
        done = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if done.get("date") != date or done.get("task") != task:
        return None

    rp = Path(request_path) if request_path else paths.REQUEST_JSON
    if rp.exists() and p.stat().st_mtime < rp.stat().st_mtime:
        return None

    # request_id 对不上也判无效（宿主愿意回填时才检查，不回填不卡）
    req = read_request(rp)
    if req and done.get("request_id") and done["request_id"] != req.get("request_id"):
        return None
    return done


def read_review_issues(done: dict[str, Any], *, min_severity: str = "high") -> list[dict[str, Any]]:
    """按 trigger_severity 过滤审稿问题（§6.4 取值约定：只有 high 触发改稿回环）。"""
    order = {"low": 0, "medium": 1, "high": 2}
    floor = order.get(min_severity, 2)
    return [i for i in (done.get("issues") or []) if order.get(str(i.get("severity")), 0) >= floor]


def clear_done(path: str | Path | None = None) -> None:
    """新起一轮之前清掉旧回执，避免上一轮的 issues 被当成这一轮的。"""
    p = Path(path) if path else paths.DONE_JSON
    if p.exists():
        p.unlink()
