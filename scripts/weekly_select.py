#!/usr/bin/env python3
"""周选题：点一下让 Claude 挑「下周每天讲什么」。

与单条选题分析（claude_select.py）的区别：任务没有单条 selection，时长可到 30 分钟，
所以单独一张 weekly_tasks 表、单独一条 worker 线程。prompt 把材料全部内联——
选题库 0-3 块、防重复台账、三池选题、候选池 stars 前 40、已占用日期——并明写
「材料已内联，不要检索项目文件」，超时上限 1800s。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import audience
import selection_db

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = PROJECT_ROOT / "output" / "selection-tasks"
TOPIC_LIBRARY = PROJECT_ROOT / "选题库.md"
EPISODES_LOG = PROJECT_ROOT / "output" / "episodes.log"
DEFAULT_CLAUDE = "claude"
DISALLOWED_TOOLS = "Bash,Edit,Write,MultiEdit,NotebookEdit"
TIMEOUT_SECONDS = 1800
CANDIDATE_LIMIT = 40
WEEKDAYS_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _bin() -> str:
    return os.environ.get("CLAUDE_BIN", DEFAULT_CLAUDE)


def next_monday(today: date | None = None) -> date:
    """下周一；周日 21:00 的 cron 跑时正好是明天。"""
    d = today or date.today()
    return d + timedelta(days=((7 - d.weekday()) % 7) or 7)


def week_dates(week_start: date) -> list[str]:
    return [(week_start + timedelta(days=i)).isoformat() for i in range(7)]


# ---------------------------------------------------------------- 材料

def _topic_library_head() -> str:
    """选题库.md 第 0-3 块全文（资格闸/困惑清单/本周主题/想听的），到「## 4.」为止。"""
    try:
        text = TOPIC_LIBRARY.read_text(encoding="utf-8")
    except OSError:
        return "（选题库.md 不存在）"
    start = text.find("## 0.")
    end = text.find("## 4.")
    if start >= 0 and end > start:
        return text[start:end].rstrip()
    return text.strip() or "（空）"


def _told_projects() -> list[str]:
    """episodes.log 全文：讲过的项目记账（只追加台账，含「选中未讲」行，宁严勿漏）。"""
    try:
        return [l.strip() for l in EPISODES_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    except OSError:
        return []


def _episode_repos() -> list[str]:
    """期次页与调研稿声明的 repos，和 episodes.log 一起当防重复台账。"""
    from workbench_server import collect_episodes, collect_research  # 延迟导入避免循环

    repos: list[str] = []
    for e in collect_episodes() + collect_research():
        repos += e.get("repos", []) or []
    return repos


def _pool_selections(db_path: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """三池选题，各附最近一次 Claude 分析的推荐结论（截断防 prompt 膨胀）。"""
    pools: dict[str, list[dict[str, Any]]] = {"inbox": [], "candidate": [], "shortlist": []}
    latest = selection_db.latest_task_by_selection(db_path)
    for s in selection_db.list_selections(db_path):
        status = s.get("status")
        if status in pools:
            task = latest.get(int(s["id"])) or {}
            try:
                rec = json.loads(task.get("result_json") or "{}")
            except json.JSONDecodeError:
                rec = {}
            s["latest_recommendation"] = rec.get("recommendation") or ""
            s["latest_why"] = (rec.get("why") or "")[:200]
            pools[status].append(s)
    return pools


def _top_candidates(db_path: str | Path | None = None, limit: int = CANDIDATE_LIMIT) -> list[dict[str, Any]]:
    """候选池 stars 降序前 N，排除已讲/已在池。prompt 里注明这只是榜单头部、不是全量。"""
    told = {r.lower() for r in _told_projects()} | {r.lower() for r in _episode_repos()}
    in_pool = {
        (s.get("project_full_name") or "").lower()
        for s in selection_db.list_selections(db_path)
        if s.get("project_full_name")
    }
    db_file = Path(db_path or selection_db.DB_PATH)
    out: list[dict[str, Any]] = []
    if not db_file.exists():
        return out
    con = sqlite3.connect("file:%s?mode=ro" % db_file, uri=True)
    con.row_factory = sqlite3.Row
    try:
        for r in con.execute(
            "select full_name, description, stars, language, category from projects order by stars desc"
        ):
            name = (r["full_name"] or "").lower()
            if not name or name in told or name in in_pool:
                continue
            out.append({
                "full_name": r["full_name"],
                "stars": r["stars"],
                "language": r["language"],
                "category": r["category"],
                "description": (r["description"] or "")[:160],
            })
            if len(out) >= limit:
                break
    finally:
        con.close()
    return out


def _occupied_dates(db_path: str | Path | None = None) -> list[str]:
    return sorted({
        s["scheduled_for"]
        for s in selection_db.list_selections(db_path)
        if s.get("status") == "scheduled" and s.get("scheduled_for")
    })


# ---------------------------------------------------------------- prompt

def build_weekly_prompt(week_start: date, db_path: str | Path | None = None) -> str:
    dates = week_dates(week_start)
    date_lines = "\n".join(
        f"- {d}（{WEEKDAYS_ZH[i]}）" for i, d in enumerate(dates)
    )
    pools = _pool_selections(db_path)
    pool_lines: list[str] = []
    for key, label in (("inbox", "灵感收件箱"), ("candidate", "本周候选/已选"), ("shortlist", "已选")):
        rows = pools.get(key) or []
        pool_lines.append(f"【{label}】{len(rows)} 条")
        for s in rows:
            rec = f"  - Claude 上次结论：{s['latest_recommendation']}——{s['latest_why']}" if s.get("latest_recommendation") else ""
            pool_lines.append(
                f"- #{s['id']} {s.get('title')}（{s.get('project_full_name') or '无项目名'}）"
                f" 来源 {s.get('source') or '手动'}"
            )
            if rec:
                pool_lines.append(rec)
    cands = _top_candidates(db_path=db_path)
    cand_lines = "\n".join(
        f"- {c['full_name']}（⭐{c['stars']:,} · {c['language'] or '?'} · {c['category'] or '未分类'}）{c['description']}"
        for c in cands
    ) or "（空）"
    occupied = "、".join(_occupied_dates(db_path)) or "无"

    return f"""你在帮一位听众排下一周的 AI 播客选题。听众画像如下，排「哪天讲什么、讲哪个角度」时一律对回这份画像：

【听众画像】
{audience.brief()}

一期讲一个主标的（撑不起就 2-3 家同主题拼盘），口吻是讲给「你」听。夜班照排期落稿，所以每天要一个能独立成稿的题。

【下周日期（共 7 天，每天一条）】
{date_lines}

【选题库第 0-3 块（资格闸最高优先；本周主题；你想听的）——这是第一输入，逐条对照】
{_topic_library_head()}

【防重复台账：以下项目已讲过或已记账，不能再当主标】
- episodes.log：
{chr(10).join('- ' + r for r in _told_projects()) or '（空）'}
- 期次/调研声明的仓库：
{chr(10).join('- ' + r for r in _episode_repos()) or '（空）'}

【三池选题（已有记录的，优先从这里安排；附 Claude 上次分析结论）】
{chr(10).join(pool_lines) or '（空）'}

【候选池 stars 降序前 {len(cands)}（只是榜单头部不是全量；上面三池都没有合适时才从这里挑）】
{cand_lines}

【下周已占用日期（已排过期的选题别重复排）】
{occupied}

硬性要求：
1. 只做排期建议。不要写稿，不要修改文件，不要执行 Bash。材料已全部内联在上文，不要去检索任何项目文件或网页。
2. 每天一条：可以是三池里的存量选题（写它的 #id 和 title），也可以是新项目（写 owner/repo，并给一句话理由）。同一主标别连排超过两天。
3. 尊重资格闸：不满足第 0 块资格的别排。每周主主题尽量对齐「本周主题」块，但个别天可以给「机动/拼盘」。
4. 结论用普通人能听懂的话，少术语。
5. 回答第一行必须是 JSON，不要 Markdown 代码块，不要额外开场白。字段固定：
{{
  "week_theme": "下周主题一句话",
  "days": [
    {{"date": "{dates[0]}", "title": "当天选题标题", "project": "owner/repo 或 拼盘：a/b + c/d 或 存量选题#id", "reason": "为什么这天讲它，2-3 句", "angles": ["拆解角度1", "角度2"], "confidence": "高|中|低"}}
    （共 7 条，date 必须与上面给的一天不差）
  ],
  "leftover": "没排进下周但值得留意的候选",
  "notes": "给排期人的提醒"
}}
"""


# ---------------------------------------------------------------- 校验

def validate_week_result(
    result: dict[str, Any], expected_dates: list[str], told: set[str]
) -> None:
    """7 天连续且与下周日期一致、project 不在已讲台账；违反直接抛错判 failed，不静默。"""
    days = result.get("days")
    if not isinstance(days, list) or len(days) != 7:
        raise ValueError("days 必须是 7 条，实际 %s" % (len(days) if isinstance(days, list) else type(days).__name__))
    got = [str(d.get("date") or "") for d in days]
    if got != expected_dates:
        raise ValueError("7 天日期必须连续且等于下周：%s" % got)
    for d in days:
        if not str(d.get("title") or "").strip():
            raise ValueError("%s 缺 title" % d.get("date"))
        project = str(d.get("project") or "").strip()
        if not project:
            raise ValueError("%s 缺 project" % d.get("date"))
        # 拼盘写法拆开逐个对台账；#id 存量选题跳过
        for token in re.split(r"[+、,，\s]+", project):
            token = token.strip().strip("`")
            if "/" in token and token.lower() in told:
                raise ValueError("%s 排了已讲过的项目：%s" % (d.get("date"), token))
        if str(d.get("confidence") or "中") not in {"高", "中", "低"}:
            d["confidence"] = "中"


def result_to_markdown(plan_id: int, week_start: str, result: dict[str, Any]) -> str:
    lines = [
        "# 人话版周选题排期",
        "",
        f"- 计划：#{plan_id}（{week_start} 那一周）",
        f"- 生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "## 下周主题",
        result.get("week_theme") or "（未给）",
        "",
    ]
    for d in result["days"]:
        angles = "；".join(d.get("angles") or [])
        lines += [
            f"## {d['date']}（{WEEKDAYS_ZH[date.fromisoformat(d['date']).weekday()]}）",
            f"- 选题：{d.get('title')}",
            f"- 标的：{d.get('project')}",
            f"- 理由：{d.get('reason')}",
            f"- 角度：{angles or '暂无'}",
            f"- 把握：{d.get('confidence') or '中'}",
            "",
        ]
    lines += ["## 没排进下周但值得留意", result.get("leftover") or "暂无", ""]
    lines += ["## 给排期人的提醒", result.get("notes") or "暂无", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- 执行

def _read_model_json(raw: str) -> dict[str, Any]:
    """优先读 claude CLI 的 envelope，再从 result 文本抽 JSON（首行或第一段花括号）。"""
    stripped = raw.strip()
    if not stripped:
        raise ValueError("Claude 没有输出")
    text = stripped
    try:
        envelope = json.loads(stripped)
        if isinstance(envelope, dict):
            text = envelope.get("result") or envelope.get("response") or envelope.get("text") or ""
            if not isinstance(text, str) or not text.strip():
                text = stripped
    except json.JSONDecodeError:
        pass
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        first_line = text.splitlines()[0].strip() if text.splitlines() else ""
        try:
            return json.loads(first_line)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            if not match:
                raise ValueError("Claude 输出里找不到 JSON")
            return json.loads(match.group(0))


def execute_weekly_task(task: dict[str, Any], db_path: str | Path | None = None) -> dict[str, Any]:
    """跑一个周选题任务：claude 子进程 → 解析校验 → 报告落盘 → plan/task 落库。

    失败一律写 result_md + failed，不静默；校验不过也是 failed（写明哪条违反）。
    """
    task_id = int(task["id"])
    plan_id = int(task["plan_id"])
    log_path = REPORT_DIR / f"weekly-{plan_id}.log"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    def _fail(message: str, exit_code: int) -> dict[str, Any]:
        selection_db.update_weekly_task(
            task_id,
            {
                "status": "failed",
                "result_json": json.dumps({"error": message}, ensure_ascii=False),
                "result_md": "## 失败\n" + message,
                "exit_code": exit_code,
                "finished_at": selection_db.now(),
            },
            db_path,
        )
        return selection_db.get_weekly_task(task_id, db_path)

    selection_db.update_weekly_task(
        task_id, {"status": "running", "log_path": str(log_path.relative_to(PROJECT_ROOT))}, db_path
    )
    bin_path = _bin()
    if not Path(bin_path).exists() and not shutil.which(bin_path):
        return _fail("找不到 Claude CLI（%s）" % bin_path, 127)

    cmd = [
        bin_path,
        "-p",
        task.get("prompt") or "",
        "--permission-mode",
        "plan",
        "--output-format",
        "json",
        "--disallowedTools",
        DISALLOWED_TOOLS,
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=PROJECT_ROOT, text=True, capture_output=True,
            timeout=TIMEOUT_SECONDS, check=False,
        )
        log_path.write_text(
            (proc.stdout or "") + ("\n--- stderr ---\n" + proc.stderr if proc.stderr else ""),
            encoding="utf-8",
        )
        if proc.returncode != 0:
            message = (proc.stderr or proc.stdout or "Claude CLI 退出码非 0").strip()[-2000:]
            return _fail(message, proc.returncode)
        result = _read_model_json(proc.stdout)
        week_start = selection_db.get_weekly_plan(plan_id, db_path)["week_start"]
        expected = week_dates(date.fromisoformat(week_start))
        told = {r.lower() for r in _told_projects() + _episode_repos()}
        validate_week_result(result, expected, told)
        md = result_to_markdown(plan_id, week_start, result)
        md_path = REPORT_DIR / f"weekly-{plan_id}.md"
        md_path.write_text(md, encoding="utf-8")
        payload = json.dumps(result, ensure_ascii=False)
        selection_db.update_weekly_task(
            task_id,
            {
                "status": "done",
                "result_json": payload,
                "result_md": md,
                "exit_code": proc.returncode,
                "finished_at": selection_db.now(),
            },
            db_path,
        )
        con = selection_db.connect(db_path)
        try:
            con.execute(
                "update weekly_plans set result_json = ?, result_md = ? where id = ?",
                (payload, md, plan_id),
            )
            con.commit()
        finally:
            con.close()
        return selection_db.get_weekly_task(task_id, db_path)
    except subprocess.TimeoutExpired as exc:
        message = "周选题任务超过 %d 分钟，已停止。" % (TIMEOUT_SECONDS // 60)
        log_path.write_text(message + ("\n" + str(exc)), encoding="utf-8")
        return _fail(message, 124)
    except Exception as exc:  # noqa: BLE001
        message = f"{type(exc).__name__}: {exc}"
        log_path.write_text(message, encoding="utf-8")
        return _fail(message, 1)


def run_worker(stop_event: Any, db_path: str | Path | None = None) -> None:
    """周任务后台串行 worker；与单条分析的 worker 分开排队，30 分钟的长任务不卡随手点的分析。"""
    while not stop_event.is_set():
        task = selection_db.claim_weekly_task(db_path)
        if not task:
            stop_event.wait(2.0)
            continue
        execute_weekly_task(task, db_path)


if __name__ == "__main__":
    # 手动跑：python3 scripts/weekly_select.py [--week 2026-09-21] --prompt-only（只看 prompt）
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="周选题排期任务")
    parser.add_argument("--week", help="下周起始（周一）YYYY-MM-DD，默认自动算下一个周一")
    parser.add_argument("--prompt-only", action="store_true", help="只打印 prompt 不执行")
    args = parser.parse_args()
    week_start = date.fromisoformat(args.week) if args.week else next_monday()
    prompt = build_weekly_prompt(week_start)
    if args.prompt_only:
        sys.stdout.write(prompt)
        raise SystemExit(0)
    created = selection_db.create_weekly_plan(week_start.isoformat(), prompt)
    print("plan #%s task #%s (reused=%s)" % (created["plan"]["id"], created["task"]["id"], created["reused"]))
    if created["reused"]:
        raise SystemExit(0)
    execute_weekly_task(created["task"])
    print("task finished:", selection_db.get_weekly_task(created["task"]["id"])["status"])
