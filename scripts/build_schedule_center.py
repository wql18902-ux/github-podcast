#!/usr/bin/env python3
"""定时任务中心 · 数据生成器（只读聚合，不做调度）。

把「调度的真身在各个面板里，本机只有文件证据」如实摆出来：
- 面板任务表：解析 `定时任务.md` 头部的实测表 + 时序总览表（时间互补）；
- DSH 会话任务：解析 `定时任务.md` 的 DSH 节（id / 时间 / 互斥提醒）；
- 项目内资产：`config/agent.json` 的 schedule 镜像、`agent/launchd/` 的未接线兜底班；
- 执行证据：`output/` 里真文件的 mtime / 首行 / 最新成品——只读，永不改它们。

红线（docs/design/GOAL.md 诚实性条款 + 任务书 §4.6）：
- 本页不做 setInterval 调度，不画不存在的按钮；
- 解析不出预期结构就整体退出（exit 1），不写半份可能误导的数据；
- 产物不含绝对路径、不含任何密钥（scripts/ 整目录进公开仓）。

用法：python3 scripts/build_schedule_center.py
产物：web/schedule/data.js（页面 <script src> 直读，file:// 可开）
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "schedule" / "data.js"

PANEL_HEADER = "| 任务 | 平台 | 实测状态"
TIMELINE_HEADER = "## 时序总览"
DSH_HEADER = "## DSH 会话定时任务"
TIME_RE = re.compile(r"\d{1,2}:\d{2}")


# ── 解析：面板实测表（`> |` 引用块里的表） ──────────────────────────

def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_sep(cells: list[str]) -> bool:
    return bool(cells) and all(set(c) <= {"-", ":", " "} for c in cells)


def parse_panel_tasks(md: str) -> list[dict]:
    """解析头部实测表。锚定在表头行上，只吃紧跟其后的 `>` 表行。"""
    lines = md.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.lstrip("> ").strip().startswith(PANEL_HEADER):
            start = i
            break
    if start is None:
        return []
    tasks: list[dict] = []
    for ln in lines[start + 1:]:
        s = ln.strip()
        if not (s.startswith(">") and "|" in s):
            break  # 表结束
        cells = _split_row(s.lstrip(">").strip())
        if len(cells) < 3 or _is_sep(cells):
            continue
        tasks.append(
            {
                "name": cells[0],
                "platform": cells[1],
                "status_raw": cells[2],
                "state": classify_state(cells[2]),
                "time": None,
                "time_note": "",
            }
        )
    return tasks


def classify_state(cell: str) -> str:
    if "ACTIVE" in cell or "现役" in cell:
        return "active"
    if "PAUSED" in cell:
        return "paused"
    if "没在跑" in cell or "❌" in cell:
        return "unregistered"
    return "unknown"


# ── 解析：时序总览表（非引用块，5 列） ──────────────────────────────

def parse_timeline(md: str) -> list[dict]:
    lines = md.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith(TIMELINE_HEADER))
    except StopIteration:
        return []
    rows: list[dict] = []
    for ln in lines[start + 1:]:
        s = ln.strip()
        if s.startswith("## "):
            break
        if not (s.startswith("|") and "|" in s[1:]):
            continue
        cells = _split_row(s)
        if len(cells) < 5 or _is_sep(cells) or cells[0] == "套":
            continue
        m = TIME_RE.search(cells[2])
        rows.append(
            {
                "suite": cells[0],
                "who": cells[1],
                "time": m.group(0) if m else None,
                "what": cells[3],
                "output": cells[4],
            }
        )
    return rows


def enrich_times(tasks: list[dict], timeline: list[dict]) -> None:
    """实测表里没写时间的任务（豆包那行），从时序总览按任务名/平台补，并标注出处。"""
    for t in tasks:
        if TIME_RE.search(t["status_raw"]):
            m = TIME_RE.search(t["status_raw"])
            t["time"] = m.group(0)
            t["time_note"] = "实测表"
            continue
        quoted = re.findall(r"「([^」]+)」", t["name"])
        bare = t["name"].split("「")[0]
        row = None
        for key in quoted + [bare, t["platform"]]:
            row = next((r for r in timeline if key and key in r["who"]), None)
            if row:
                break
        if row and row["time"]:
            t["time"] = row["time"]
            t["time_note"] = f"时序总览（{row['suite']}，文档记载）"
        else:
            t["time_note"] = "没查到时间"


# ── 解析：DSH 会话任务 ─────────────────────────────────────────────

def parse_dsh(md: str) -> dict | None:
    lines = md.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith(DSH_HEADER))
    except StopIteration:
        return None
    body = []
    for ln in lines[start + 1:]:
        if ln.startswith("## "):
            break
        body.append(ln)
    text = "\n".join(body)
    if "schedule-" not in text:
        return None
    idm = re.search(r"(schedule-[0-9a-f-]{20,50})", text)
    tm = re.search(r"每天\s*(\d{1,2}:\d{2})（(America/[A-Za-z_/]+)）", text)
    fr = re.search(r"首跑\s*(\d{4}-\d{2}-\d{2})", text)
    return {
        "name": "AI 周节目一条龙（写稿 → MiMo 合成 → 推飞书 → 网易云+夸克）",
        "platform": "DSH 会话",
        "task_id": idm.group(1) if idm else None,
        "time": tm.group(1) if tm else None,
        "tz": tm.group(2) if tm else None,
        "first_run": fr.group(1) if fr else None,
        "state": "session",  # 会话内调度，本机读不到运行状态
        "note": "与 WorkBuddy 00:34 写稿任务互斥（都写 output/latest-script.md）；"
        "机器睡眠或 DSH 退出会错过。",
        "control": "DSH 会话内 schedule_update / schedule_delete",
    }


# ── 采集：项目内资产与执行证据 ──────────────────────────────────────

def collect_agent_mirror() -> dict:
    cfg = json.loads((ROOT / "config" / "agent.json").read_text(encoding="utf-8"))
    return {
        "schedule": cfg.get("schedule", {}),
        "host_current": cfg.get("host", {}).get("current"),
        "synth_primary": cfg.get("synth", {}).get("primary"),
        "synth_fallback": cfg.get("synth", {}).get("fallback"),
        "synth_routes": sorted(cfg.get("synth", {}).get("routes", {}).keys()),
        "note": cfg.get("schedule", {}).get("_note", ""),
    }


def collect_launchd() -> list[dict]:
    try:
        res = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, timeout=10
        )
        loaded = res.stdout or ""
    except (OSError, subprocess.SubprocessError):
        loaded = ""
    out = []
    for plist in sorted((ROOT / "agent" / "launchd").glob("*.plist")):
        xml = plist.read_text(encoding="utf-8")
        m = re.search(r"<key>Label</key>\s*<string>([^<]+)</string>", xml)
        label = m.group(1) if m else plist.stem
        out.append(
            {
                "file": f"agent/launchd/{plist.name}",
                "label": label,
                "loaded": (label in loaded) if loaded else None,
                "state": "loaded" if label in loaded else "未接线",
                "note": "装之前的三条前提见 agent/launchd/README.md",
            }
        )
    return out


def collect_evidence(now: datetime) -> dict:
    ev: dict = {}

    status_path = ROOT / "output" / "latest-status.txt"
    status_line = ""
    if status_path.exists():
        for ln in status_path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                status_line = ln.strip()
                break
    code = status_line.split()[0] if status_line else None
    dm = re.search(r"\d{4}-\d{2}-\d{2}", status_line)
    epm = re.search(r"ep\d+", status_line)
    ev["latest_status"] = {
        "line": status_line,
        "code": code,
        "date": dm.group(0) if dm else None,
        "ep": epm.group(0) if epm else None,
        "path": "output/latest-status.txt",
    }

    script_p = ROOT / "output" / "latest-script.md"
    if script_p.exists():
        mtime = datetime.fromtimestamp(script_p.stat().st_mtime)
        ev["latest_script"] = {
            "path": "output/latest-script.md",
            "mtime": mtime.isoformat(timespec="minutes"),
            "age_hours": round((now - mtime).total_seconds() / 3600, 1),
        }

    log_p = ROOT / "output" / "episodes.log"
    if log_p.exists():
        last = ""
        for ln in log_p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                last = ln.strip()
        ev["episodes_log_last"] = {"line": last[:200], "path": "output/episodes.log"}

    audio_dir = ROOT / "output" / "audio"
    if audio_dir.is_dir():
        files = [p for p in audio_dir.iterdir() if p.is_file()]
        if files:
            newest = max(files, key=lambda p: p.stat().st_mtime)
            mt = datetime.fromtimestamp(newest.stat().st_mtime)
            ev["latest_audio"] = {
                "name": newest.name,
                "mtime": mt.isoformat(timespec="minutes"),
                "size_mb": round(newest.stat().st_size / 1_000_000, 1),
                "path": "output/audio/",
            }
    return ev


def _mtime_iso(rel: str) -> str | None:
    p = ROOT / rel
    if not p.exists():
        return None
    return datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes")


# ── 主流程 ─────────────────────────────────────────────────────────

CONTROL = {
    "WorkBuddy": "WorkBuddy 自动化面板",
    "豆包 App": "豆包 App 内",
}

def main() -> int:
    now = datetime.now()
    md_path = ROOT / "定时任务.md"
    md = md_path.read_text(encoding="utf-8")

    tasks = parse_panel_tasks(md)
    timeline = parse_timeline(md)
    enrich_times(tasks, timeline)
    for t in tasks:
        t["control"] = CONTROL.get(t["platform"], "—（没挂任何平台）")

    dsh = parse_dsh(md)
    errors = []
    if len(tasks) < 4:
        errors.append(f"实测表只解析到 {len(tasks)} 行（预期 ≥4），表结构可能变了")
    if dsh is None:
        errors.append("没找到 DSH 会话任务节")
    try:
        mirror = collect_agent_mirror()
    except (OSError, json.JSONDecodeError) as e:
        errors.append(f"config/agent.json 读不了：{e}")
        mirror = {}
    if errors:
        print("[!] 定时任务中心数据不完整，拒绝生成：", file=sys.stderr)
        for e in errors:
            print(f"    - {e}", file=sys.stderr)
        return 1

    data = {
        "version": 1,
        "readonly": True,
        "generated_at": now.isoformat(timespec="minutes"),
        "disclaimer": "调度真身在各平台面板（WorkBuddy / 豆包 / DSH）：改时间、开关只能在面板里动，"
        "文件系统改不了（定时任务.md 2026-09-21 面板实测口径）。本页只聚合文件证据。",
        "panel_tasks": tasks,
        "dsh_task": dsh,
        "agent_mirror": mirror,
        "launchd_assets": collect_launchd(),
        "evidence": collect_evidence(now),
        "sources": [
            {"path": rel, "mtime": _mtime_iso(rel)}
            for rel in [
                "定时任务.md",
                "config/agent.json",
                "output/latest-status.txt",
                "output/latest-script.md",
                "output/episodes.log",
            ]
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=1)
    OUT.write_text(
        "/* 自动生成，别手改；来源 scripts/build_schedule_center.py */\n"
        f"window.SCHEDULE_CENTER = {payload};\n",
        encoding="utf-8",
    )
    active = sum(1 for t in tasks if t["state"] == "active")
    print(f"[✓] {OUT.relative_to(ROOT)}：面板任务 {len(tasks)} 条（现役 {active}），"
          f"DSH {dsh['time']} {dsh['tz']}，launchd 资产 {len(data['launchd_assets'])} 项")
    return 0


if __name__ == "__main__":
    sys.exit(main())
