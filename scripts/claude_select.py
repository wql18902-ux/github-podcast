#!/usr/bin/env python3
"""Claude 选题分析任务。

只让 Claude 做选题判断，不改文件、不写稿、不触发合成。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import audience
import selection_db

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = PROJECT_ROOT / "output" / "selection-tasks"
DEFAULT_CLAUDE = "claude"
DISALLOWED_TOOLS = "Bash,Edit,Write,MultiEdit,NotebookEdit"


def _bin() -> str:
    return os.environ.get("CLAUDE_BIN", DEFAULT_CLAUDE)


def build_prompt(selection: dict[str, Any]) -> str:
    """生成给 Claude 的选题分析提示词。"""
    title = selection.get("title") or "未命名选题"
    kind = "灵感" if selection.get("kind") == "idea" else "GitHub 项目"
    url = selection.get("url") or "没有链接"
    project = selection.get("project_full_name") or "没有项目名"
    summary = selection.get("summary") or "没有一句话说明"
    why = selection.get("why") or "没有补充理由"
    source = selection.get("source") or "没有来源"

    return f"""你在帮一位听众判断一个 AI 播客选题。听众画像如下，判断「值不值得讲、能怎么用」时一律对回这份画像：

【听众画像】
{audience.brief()}

选题信息：
- 标题：{title}
- 类型：{kind}
- 项目名：{project}
- 链接：{url}
- 一句话说明：{summary}
- 为什么值得讲：{why}
- 来源：{source}

硬性要求：
1. 只做选题分析。不要写播客稿，不要修改文件，不要执行 Bash，不要提交合成任务。
2. 如果链接或信息不够，就基于已有信息判断，并明确说「证据不足」；不要编造版本号、Star 数、文件名或函数名。
3. 结论要用普通人能听懂的话，少术语；必须提技术细节时顺手解释它是什么。
4. 回答第一行必须是 JSON，不要 Markdown 代码块，不要额外开场白。
5. JSON 固定使用这些字段：
{{
  "recommendation": "强烈推荐 | 可以讲 | 先放放 | 不建议",
  "why": "为什么值得讲，2 到 4 句",
  "angles": ["具体拆解角度 1", "具体拆解角度 2", "具体拆解角度 3"],
  "usage": ["以后能怎么用 1", "以后能怎么用 2", "以后能怎么用 3"],
  "risks": "风险、坑或不推荐理由",
  "standard": "一条判断标准"
}}
"""


def _read_json_text(raw: str) -> dict[str, Any]:
    """优先读 Claude CLI 的 envelope，再从 result 里抽 JSON。"""
    stripped = raw.strip()
    if not stripped:
        raise ValueError("Claude 没有输出")
    try:
        envelope = json.loads(stripped)
        if isinstance(envelope, dict):
            text = envelope.get("result") or envelope.get("response") or envelope.get("text") or ""
            if isinstance(text, str) and text.strip():
                return _parse_model_json(text)
            # 有些版本可能直接把业务 JSON 放在顶层
            if {"recommendation", "why", "angles", "usage", "risks", "standard"} <= set(envelope):
                return _normalize(envelope)
    except json.JSONDecodeError:
        pass
    return _parse_model_json(stripped)


def _parse_model_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return _normalize(json.loads(text))
    except json.JSONDecodeError:
        # 兜底：从回答里抽第一段花括号 JSON。
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise ValueError("Claude 输出不是 JSON")
        return _normalize(json.loads(match.group(0)))


def _normalize(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Claude JSON 不是对象")

    def one(key: str) -> str:
        v = data.get(key, "")
        if isinstance(v, list):
            return "\n".join(str(x) for x in v if str(x).strip())
        return str(v or "").strip()

    angles = data.get("angles", [])
    usage = data.get("usage", [])
    if not isinstance(angles, list):
        angles = [str(angles)]
    if not isinstance(usage, list):
        usage = [str(usage)]
    recommendation = one("recommendation")
    if recommendation not in {"强烈推荐", "可以讲", "先放放", "不建议"}:
        raise ValueError("推荐指数不合法：%s" % (recommendation or "空"))
    if not one("why") or not one("standard"):
        raise ValueError("Claude JSON 缺少 why 或 standard")
    return {
        "recommendation": recommendation,
        "why": one("why"),
        "angles": [str(x).strip() for x in angles if str(x).strip()],
        "usage": [str(x).strip() for x in usage if str(x).strip()],
        "risks": one("risks"),
        "standard": one("standard"),
    }


def result_to_markdown(task_id: int, selection: dict[str, Any], result: dict[str, Any]) -> str:
    lines = [
        "# 人话版选题报告",
        "",
        f"- 选题：{selection.get('title', '')}",
        f"- 任务：#{task_id}",
        f"- 生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "## 推荐指数",
        result["recommendation"],
        "",
        "## 为什么值得讲",
        result["why"],
        "",
        "## 具体拆解角度",
    ]
    lines += [f"{i}. {x}" for i, x in enumerate(result["angles"], 1)] or ["暂无"]
    lines += ["", "## 你以后能怎么用"]
    lines += [f"{i}. {x}" for i, x in enumerate(result["usage"], 1)] or ["暂无"]
    lines += [
        "",
        "## 风险或不推荐理由",
        result.get("risks") or "暂无",
        "",
        "## 一条判断标准",
        result["standard"],
        "",
    ]
    return "\n".join(lines)


def execute_task(task: dict[str, Any], db_path: str | Path | None = None) -> dict[str, Any]:
    task_id = int(task["id"])
    selection = selection_db.get_selection(int(task["selection_id"]), db_path)
    prompt = task.get("prompt") or build_prompt(selection)
    log_path = REPORT_DIR / f"task-{task_id}.log"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    selection_db.update_task(
        task_id,
        {"status": "running", "log_path": str(log_path.relative_to(PROJECT_ROOT))},
        db_path,
    )
    bin_path = _bin()
    if not Path(bin_path).exists() and not shutil.which(bin_path):
        return selection_db.update_task(
            task_id,
            {
                "status": "failed",
                "result_json": json.dumps({"error": "找不到 Claude CLI"}, ensure_ascii=False),
                "result_md": "## 失败\n找不到 Claude CLI。",
                "exit_code": 127,
                "finished_at": selection_db.now(),
            },
            db_path,
        )

    cmd = [
        bin_path,
        "-p",
        prompt,
        "--permission-mode",
        "plan",
        "--output-format",
        "json",
        "--disallowedTools",
        DISALLOWED_TOOLS,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            timeout=900,
            check=False,
        )
        log_path.write_text(
            (proc.stdout or "") + ("\n--- stderr ---\n" + proc.stderr if proc.stderr else ""),
            encoding="utf-8",
        )
        if proc.returncode != 0:
            message = (proc.stderr or proc.stdout or "Claude CLI 退出码非 0").strip()[-2000:]
            return selection_db.update_task(
                task_id,
                {
                    "status": "failed",
                    "result_json": json.dumps({"error": message}, ensure_ascii=False),
                    "result_md": "## 失败\n```\n" + message + "\n```",
                    "exit_code": proc.returncode,
                    "finished_at": selection_db.now(),
                },
                db_path,
            )
        result = _read_json_text(proc.stdout)
        md = result_to_markdown(task_id, selection, result)
        md_path = REPORT_DIR / f"task-{task_id}.md"
        md_path.write_text(md, encoding="utf-8")
        return selection_db.update_task(
            task_id,
            {
                "status": "done",
                "result_json": json.dumps(result, ensure_ascii=False),
                "result_md": md,
                "exit_code": proc.returncode,
                "finished_at": selection_db.now(),
            },
            db_path,
        )
    except subprocess.TimeoutExpired as exc:
        message = "Claude 任务超过 15 分钟，已停止。"
        log_path.write_text(message + ("\n" + str(exc)), encoding="utf-8")
        return selection_db.update_task(
            task_id,
            {
                "status": "failed",
                "result_json": json.dumps({"error": message}, ensure_ascii=False),
                "result_md": "## 失败\n" + message,
                "exit_code": 124,
                "finished_at": selection_db.now(),
            },
            db_path,
        )
    except Exception as exc:  # noqa: BLE001
        message = f"{type(exc).__name__}: {exc}"
        log_path.write_text(message, encoding="utf-8")
        return selection_db.update_task(
            task_id,
            {
                "status": "failed",
                "result_json": json.dumps({"error": message}, ensure_ascii=False),
                "result_md": "## 失败\n" + message,
                "exit_code": 1,
                "finished_at": selection_db.now(),
            },
            db_path,
        )


def run_worker(stop_event: Any, db_path: str | Path | None = None) -> None:
    """后台串行 worker；server 只启动一个。"""
    while not stop_event.is_set():
        task = selection_db.claim_task(db_path)
        if not task:
            stop_event.wait(1.0)
            continue
        execute_task(task, db_path)
