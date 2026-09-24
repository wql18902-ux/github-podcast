#!/usr/bin/env python3
"""选题台数据库层。

info_source.db 仍是唯一真相源；这里只加表，不改 fetch.py 抓取逻辑。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("GITHUB_PODCAST_DB", PROJECT_ROOT / "info_source.db"))

SELECTION_STATUSES = {
    "inbox",
    "candidate",
    "shortlist",
    "rejected",
    "scheduled",
    "used",
    "archived",
}
TASK_STATUSES = {"queued", "running", "done", "failed"}
KINDS = {"idea", "project"}
DEFAULT_PRIORITY = 2


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path or DB_PATH)
    con = sqlite3.connect(str(p), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys = on")
    con.execute("pragma busy_timeout = 5000")
    return con


def init_db(path: str | Path | None = None) -> Path:
    """建表；重复执行不会重建已有表，也不会影响 projects。"""
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = connect(p)
    try:
        con.executescript(
            """
            create table if not exists selections (
                id integer primary key autoincrement,
                title text not null,
                kind text not null default 'idea',
                project_full_name text,
                url text,
                summary text,
                why text,
                status text not null default 'inbox',
                priority integer not null default 2,
                scheduled_for text,
                source text not null default '手动',
                created_at text not null,
                updated_at text not null,
                lark_record_id text
            );

            create table if not exists selection_tasks (
                id integer primary key autoincrement,
                selection_id integer not null,
                status text not null default 'queued',
                prompt text not null,
                result_json text,
                result_md text,
                log_path text,
                exit_code integer,
                created_at text not null,
                finished_at text,
                foreign key (selection_id) references selections(id)
            );

            create table if not exists feishu_sync_state (
                id integer primary key autoincrement,
                selection_id integer not null unique,
                base_token text not null,
                table_id text not null,
                record_id text,
                remote_updated_at text,
                remote_hash text,
                sync_status text not null default 'ok',
                conflict_info text,
                last_synced_at text,
                created_at text not null,
                updated_at text not null,
                foreign key (selection_id) references selections(id)
            );

            /* 周选题：plan 是一份「下周 7 天建议」，task 是跑它的 claude 子进程。
               不复用 selection_tasks——那边 selection_id not null 外键，周任务没有单条选题 */
            create table if not exists weekly_plans (
                id integer primary key autoincrement,
                week_start text not null,
                status text not null default 'proposed',
                result_json text,
                result_md text,
                created_at text not null,
                confirmed_at text
            );

            create table if not exists weekly_tasks (
                id integer primary key autoincrement,
                plan_id integer not null,
                status text not null default 'queued',
                prompt text not null,
                result_json text,
                result_md text,
                log_path text,
                exit_code integer,
                created_at text not null,
                finished_at text,
                foreign key (plan_id) references weekly_plans(id)
            );

            /* 讲稿推送台账：一期一条（date 主键）。file_md5 判「稿子变没变」（幂等），
               file_token 记上一次推上去的附件——lark 的 upload 是 append 语义，
               不记 token 就会在同一格里越堆越多，删不掉 */
            create table if not exists script_pushes (
                date text primary key,
                selection_id integer,
                record_id text,
                file_name text,
                file_md5 text,
                file_token text,
                pushed_at text
            );

            create index if not exists idx_selections_status
                on selections(status, updated_at desc);
            create index if not exists idx_tasks_selection
                on selection_tasks(selection_id, id desc);
            create index if not exists idx_feishu_record
                on feishu_sync_state(record_id);
            create index if not exists idx_weekly_tasks_plan
                on weekly_tasks(plan_id, id desc);
            """
        )
        # 幂等迁移：给已有库补 scheduled_for（排期日期，YYYY-MM-DD）。
        # 常驻服务重启时跑一次即可，pragma 查列避免重复 ALTER 报错
        cols = {r[1] for r in con.execute("pragma table_info(selections)")}
        if "scheduled_for" not in cols:
            con.execute("alter table selections add column scheduled_for text")
            con.commit()
        con.commit()
    finally:
        con.close()
    return p


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    text_fields = (
        "title",
        "kind",
        "project_full_name",
        "url",
        "summary",
        "why",
        "status",
        "source",
        "lark_record_id",
    )
    for key in text_fields:
        if key in data:
            value = data[key]
            out[key] = str(value).strip() if value is not None else None
    if "priority" in data and data["priority"] is not None:
        try:
            out["priority"] = max(1, min(3, int(data["priority"])))
        except (TypeError, ValueError):
            raise ValueError("优先级必须是 1、2 或 3")
    if "scheduled_for" in data:
        value = data["scheduled_for"]
        if value is None or str(value).strip() == "":
            out["scheduled_for"] = None
        else:
            v = str(value).strip()
            try:
                datetime.fromisoformat(v)
            except ValueError:
                raise ValueError("排期日期必须是 YYYY-MM-DD")
            out["scheduled_for"] = v
    return out


def create_selection(data: dict[str, Any], path: str | Path | None = None) -> dict[str, Any]:
    init_db(path)
    row = _clean(data)
    title = row.get("title")
    if not title:
        raise ValueError("标题不能为空")
    kind = row.get("kind") or "idea"
    if kind not in KINDS:
        raise ValueError("类型只能是 idea 或 project")
    status = row.get("status") or ("candidate" if kind == "project" else "inbox")
    if status not in SELECTION_STATUSES:
        raise ValueError("未知状态：%s" % status)
    source = row.get("source") or "手动"
    ts = now()
    con = connect(path)
    try:
        cur = con.execute(
            """insert into selections
               (title, kind, project_full_name, url, summary, why, status,
                priority, source, created_at, updated_at, lark_record_id)
               values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                title,
                kind,
                row.get("project_full_name"),
                row.get("url"),
                row.get("summary"),
                row.get("why"),
                status,
                row.get("priority", DEFAULT_PRIORITY),
                source,
                ts,
                ts,
                row.get("lark_record_id"),
            ),
        )
        con.commit()
        return get_selection(cur.lastrowid, path)
    finally:
        con.close()


def get_selection(selection_id: int, path: str | Path | None = None) -> dict[str, Any]:
    con = connect(path)
    try:
        r = con.execute("select * from selections where id = ?", (selection_id,)).fetchone()
        return dict(r) if r else {}
    finally:
        con.close()


def list_selections(
    path: str | Path | None = None,
    status: str | None = None,
    include_archived: bool = True,
) -> list[dict[str, Any]]:
    con = connect(path)
    try:
        if status:
            rows = con.execute(
                "select * from selections where status = ? order by updated_at desc, id desc",
                (status,),
            ).fetchall()
        elif include_archived:
            rows = con.execute("select * from selections order by updated_at desc, id desc").fetchall()
        else:
            rows = con.execute(
                "select * from selections where status != 'archived' order by updated_at desc, id desc"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def update_selection(
    selection_id: int,
    data: dict[str, Any],
    path: str | Path | None = None,
) -> dict[str, Any]:
    init_db(path)
    row = _clean(data)
    if "status" in row and row["status"] not in SELECTION_STATUSES:
        raise ValueError("未知状态：%s" % row["status"])
    if "kind" in row and row["kind"] not in KINDS:
        raise ValueError("类型只能是 idea 或 project")
    if not row:
        raise ValueError("没有可更新字段")
    row["updated_at"] = now()
    keys = list(row)
    sets = ", ".join("%s = ?" % k for k in keys)
    con = connect(path)
    try:
        cur = con.execute(
            "update selections set %s where id = ?" % sets,
            [row[k] for k in keys] + [selection_id],
        )
        con.commit()
        if cur.rowcount != 1:
            raise ValueError("选题不存在：%s" % selection_id)
        return get_selection(selection_id, path)
    finally:
        con.close()


def create_task(
    selection_id: int,
    prompt: str,
    path: str | Path | None = None,
) -> dict[str, Any]:
    init_db(path)
    con = connect(path)
    try:
        exists = con.execute("select id from selections where id = ?", (selection_id,)).fetchone()
        if not exists:
            raise ValueError("选题不存在：%s" % selection_id)
        ts = now()
        cur = con.execute(
            """insert into selection_tasks
               (selection_id, status, prompt, created_at)
               values (?, 'queued', ?, ?)""",
            (selection_id, prompt, ts),
        )
        con.commit()
        return get_task(cur.lastrowid, path)
    finally:
        con.close()


def get_task(task_id: int, path: str | Path | None = None) -> dict[str, Any]:
    con = connect(path)
    try:
        r = con.execute("select * from selection_tasks where id = ?", (task_id,)).fetchone()
        return dict(r) if r else {}
    finally:
        con.close()


def list_tasks(path: str | Path | None = None, limit: int = 100) -> list[dict[str, Any]]:
    con = connect(path)
    try:
        rows = con.execute(
            "select * from selection_tasks order by id desc limit ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def update_task(task_id: int, data: dict[str, Any], path: str | Path | None = None) -> dict[str, Any]:
    init_db(path)
    allowed = {"status", "result_json", "result_md", "log_path", "exit_code", "finished_at"}
    row = {k: v for k, v in data.items() if k in allowed}
    if "status" in row and row["status"] not in TASK_STATUSES:
        raise ValueError("未知任务状态：%s" % row["status"])
    if not row:
        raise ValueError("没有可更新任务字段")
    keys = list(row)
    sets = ", ".join("%s = ?" % k for k in keys)
    con = connect(path)
    try:
        cur = con.execute(
            "update selection_tasks set %s where id = ?" % sets,
            [row[k] for k in keys] + [task_id],
        )
        con.commit()
        if cur.rowcount != 1:
            raise ValueError("任务不存在：%s" % task_id)
        return get_task(task_id, path)
    finally:
        con.close()


def claim_task(path: str | Path | None = None) -> dict[str, Any] | None:
    """取最早的 queued 任务并改成 running，保证 worker 内串行。"""
    con = connect(path)
    try:
        r = con.execute(
            "select * from selection_tasks where status = 'queued' order by id limit 1"
        ).fetchone()
        if not r:
            return None
        con.execute(
            "update selection_tasks set status = 'running' where id = ?", (r["id"],)
        )
        con.commit()
        return dict(r)
    finally:
        con.close()


def reset_interrupted_tasks(path: str | Path | None = None) -> int:
    con = connect(path)
    try:
        cur = con.execute(
            "update selection_tasks set status = 'queued' where status = 'running'"
        )
        cur2 = con.execute(
            "update weekly_tasks set status = 'queued' where status = 'running'"
        )
        con.commit()
        return cur.rowcount + cur2.rowcount
    finally:
        con.close()


# ---------------------------------------------------------------- 周选题

def create_weekly_plan(
    week_start: str, prompt: str, path: str | Path | None = None
) -> dict[str, Any]:
    """建 plan + task；同周已有 proposed 且任务还在排队/执行中则幂等复用，不重建。"""
    init_db(path)
    con = connect(path)
    try:
        row = con.execute(
            "select * from weekly_plans where week_start = ? and status = 'proposed'"
            " order by id desc limit 1",
            (week_start,),
        ).fetchone()
        if row:
            task = con.execute(
                "select * from weekly_tasks where plan_id = ? order by id desc limit 1",
                (row["id"],),
            ).fetchone()
            if task and task["status"] in ("queued", "running"):
                return {"plan": dict(row), "task": dict(task), "reused": True}
        ts = now()
        plan_id = con.execute(
            "insert into weekly_plans (week_start, status, created_at) values (?, 'proposed', ?)",
            (week_start, ts),
        ).lastrowid
        task_id = con.execute(
            "insert into weekly_tasks (plan_id, status, prompt, created_at)"
            " values (?, 'queued', ?, ?)",
            (plan_id, prompt, ts),
        ).lastrowid
        con.commit()
        plan = dict(con.execute("select * from weekly_plans where id = ?", (plan_id,)).fetchone())
        task = dict(con.execute("select * from weekly_tasks where id = ?", (task_id,)).fetchone())
        return {"plan": plan, "task": task, "reused": False}
    finally:
        con.close()


def get_weekly_plan(plan_id: int, path: str | Path | None = None) -> dict[str, Any] | None:
    con = connect(path)
    try:
        r = con.execute("select * from weekly_plans where id = ?", (plan_id,)).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def latest_weekly_plans(path: str | Path | None = None, limit: int = 5) -> list[dict[str, Any]]:
    con = connect(path)
    try:
        rows = con.execute(
            "select * from weekly_plans order by id desc limit ?", (limit,)
        ).fetchall()
        out = []
        for r in rows:
            plan = dict(r)
            task = con.execute(
                "select id, status, exit_code, finished_at, log_path from weekly_tasks"
                " where plan_id = ? order by id desc limit 1",
                (plan["id"],),
            ).fetchone()
            plan["latest_task"] = dict(task) if task else None
            out.append(plan)
        return out
    finally:
        con.close()


def get_weekly_task(task_id: int, path: str | Path | None = None) -> dict[str, Any] | None:
    con = connect(path)
    try:
        r = con.execute("select * from weekly_tasks where id = ?", (task_id,)).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def update_weekly_task(
    task_id: int, data: dict[str, Any], path: str | Path | None = None
) -> dict[str, Any]:
    init_db(path)
    row = dict(data)
    if "status" in row and row["status"] not in {"queued", "running", "done", "failed"}:
        raise ValueError("未知周任务状态：%s" % row["status"])
    con = connect(path)
    try:
        keys = list(row)
        sets = ", ".join("%s = ?" % k for k in keys)
        cur = con.execute(
            "update weekly_tasks set %s where id = ?" % sets,
            [row[k] for k in keys] + [task_id],
        )
        con.commit()
        if cur.rowcount != 1:
            raise ValueError("周任务不存在：%s" % task_id)
        r = con.execute("select * from weekly_tasks where id = ?", (task_id,)).fetchone()
        return dict(r)
    finally:
        con.close()


def claim_weekly_task(path: str | Path | None = None) -> dict[str, Any] | None:
    con = connect(path)
    try:
        con.execute("pragma busy_timeout = 5000")
        r = con.execute(
            "select * from weekly_tasks where status = 'queued' order by id limit 1"
        ).fetchone()
        if not r:
            return None
        con.execute("update weekly_tasks set status = 'running' where id = ?", (r["id"],))
        con.commit()
        return dict(r)
    finally:
        con.close()


def confirm_weekly_plan(
    plan_id: int,
    adopt: dict[str, bool],
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """把周计划确认落库成排期。adopt: {date: 是否采纳}。

    每天一条：project 写「#N」指存量选题 id；owner/repo 小写匹配既有选题 → 更新为
    scheduled + scheduled_for（匹配不到就新建 source='周选题'）；没有项目名的按机动日
    落灵感型排期。同一选题被多天引用时后写覆盖（结果面板逐天可见，人工过目）。
    单事务，任何一天失败回滚整批。
    """
    plan = get_weekly_plan(plan_id, path)
    if not plan:
        raise ValueError("周计划不存在：%s" % plan_id)
    if not plan.get("result_json"):
        raise ValueError("周计划还没有结果，不能确认")
    try:
        days = json.loads(plan["result_json"]).get("days", [])
    except json.JSONDecodeError as exc:
        raise ValueError("周计划结果不是 JSON：%s" % exc)
    con = connect(path)
    results: list[dict[str, Any]] = []
    try:
        con.execute("pragma busy_timeout = 5000")
        con.execute("begin")
        ts = now()
        for day in days:
            d = str(day.get("date") or "")
            if not adopt.get(d):
                continue
            title = str(day.get("title") or "").strip()
            project = str(day.get("project") or "").strip()
            reason = str(day.get("reason") or "").strip()
            if not title or not d:
                raise ValueError("有一天缺日期或标题，整批不落")
            ref = re.search(r"#(\d+)", project)
            if ref:
                r = con.execute(
                    "select id from selections where id = ?", (int(ref.group(1)),)
                ).fetchone()
                if r:
                    con.execute(
                        "update selections set status = 'scheduled', scheduled_for = ?,"
                        " title = ?, updated_at = ? where id = ?",
                        (d, title, ts, r["id"]),
                    )
                    results.append({"date": d, "action": "updated", "selection_id": r["id"], "title": title})
                    continue
            token = next(
                (
                    t.strip().strip("`")
                    for t in re.split(r"[+、,，\s]+", project)
                    if "/" in t
                ),
                None,
            )
            if token:
                r = con.execute(
                    "select id from selections where lower(project_full_name) = ?"
                    " order by id desc limit 1",
                    (token.lower(),),
                ).fetchone()
                if r:
                    con.execute(
                        "update selections set status = 'scheduled', scheduled_for = ?,"
                        " title = ?, updated_at = ? where id = ?",
                        (d, title, ts, r["id"]),
                    )
                    results.append({"date": d, "action": "updated", "selection_id": r["id"], "title": title})
                    continue
                cur = con.execute(
                    "insert into selections (title, kind, project_full_name, url, summary,"
                    " status, scheduled_for, source, created_at, updated_at)"
                    " values (?, 'project', ?, ?, ?, 'scheduled', ?, '周选题', ?, ?)",
                    (title, token, "https://github.com/" + token, reason, d, ts, ts),
                )
                results.append({"date": d, "action": "created", "selection_id": cur.lastrowid, "title": title})
            else:
                cur = con.execute(
                    "insert into selections (title, kind, summary, status, scheduled_for,"
                    " source, created_at, updated_at)"
                    " values (?, 'idea', ?, 'scheduled', ?, '周选题', ?, ?)",
                    (title, reason, d, ts, ts),
                )
                results.append({"date": d, "action": "created", "selection_id": cur.lastrowid, "title": title})
        con.execute(
            "update weekly_plans set status = 'confirmed', confirmed_at = ? where id = ?",
            (ts, plan_id),
        )
        con.commit()
        return results
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def latest_task_by_selection(path: str | Path | None = None) -> dict[int, dict[str, Any]]:
    con = connect(path)
    try:
        rows = con.execute(
            """select t.* from selection_tasks t
               join (
                   select selection_id, max(id) as max_id
                   from selection_tasks group by selection_id
               ) x on x.max_id = t.id"""
        ).fetchall()
        return {int(r["selection_id"]): dict(r) for r in rows}
    finally:
        con.close()


def set_feishu_state(
    selection_id: int,
    base_token: str,
    table_id: str,
    record_id: str | None,
    remote_updated_at: str | None = None,
    remote_hash: str | None = None,
    sync_status: str = "ok",
    conflict_info: str | None = None,
    path: str | Path | None = None,
) -> None:
    init_db(path)
    ts = now()
    con = connect(path)
    try:
        con.execute(
            """insert into feishu_sync_state
               (selection_id, base_token, table_id, record_id, remote_updated_at,
                remote_hash, sync_status, conflict_info, last_synced_at, created_at, updated_at)
               values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               on conflict(selection_id) do update set
                 base_token = excluded.base_token,
                 table_id = excluded.table_id,
                 record_id = coalesce(excluded.record_id, feishu_sync_state.record_id),
                 remote_updated_at = excluded.remote_updated_at,
                 remote_hash = excluded.remote_hash,
                 sync_status = excluded.sync_status,
                 conflict_info = excluded.conflict_info,
                 last_synced_at = excluded.last_synced_at,
                 updated_at = excluded.updated_at""",
            (
                selection_id,
                base_token,
                table_id,
                record_id,
                remote_updated_at,
                remote_hash,
                sync_status,
                conflict_info,
                ts,
                ts,
                ts,
            ),
        )
        con.commit()
    finally:
        con.close()


def feishu_states(path: str | Path | None = None) -> dict[int, dict[str, Any]]:
    con = connect(path)
    try:
        rows = con.execute("select * from feishu_sync_state").fetchall()
        return {int(r["selection_id"]): dict(r) for r in rows}
    finally:
        con.close()


# ---------------------------------------------------------------- 讲稿推送台账

def selection_scheduled_for(date: str, path: str | Path | None = None) -> dict[str, Any]:
    """取某天排期的选题。同一天可能有多条，优先挑了飞书 record_id 的那条。"""
    con = connect(path)
    try:
        rows = con.execute(
            "select * from selections where scheduled_for = ?"
            " order by (lark_record_id is null), id desc",
            (date,),
        ).fetchall()
        return dict(rows[0]) if rows else {}
    finally:
        con.close()


def get_script_push(date: str, path: str | Path | None = None) -> dict[str, Any]:
    con = connect(path)
    try:
        r = con.execute("select * from script_pushes where date = ?", (date,)).fetchone()
        return dict(r) if r else {}
    finally:
        con.close()


def set_script_push(
    date: str,
    selection_id: int | None,
    record_id: str,
    file_name: str,
    file_md5: str,
    file_token: str | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    init_db(path)
    ts = now()
    con = connect(path)
    try:
        con.execute(
            """insert into script_pushes
               (date, selection_id, record_id, file_name, file_md5, file_token, pushed_at)
               values (?, ?, ?, ?, ?, ?, ?)
               on conflict(date) do update set
                 selection_id = excluded.selection_id,
                 record_id = excluded.record_id,
                 file_name = excluded.file_name,
                 file_md5 = excluded.file_md5,
                 file_token = coalesce(excluded.file_token, script_pushes.file_token),
                 pushed_at = excluded.pushed_at""",
            (date, selection_id, record_id, file_name, file_md5, file_token, ts),
        )
        con.commit()
        return get_script_push(date, path)
    finally:
        con.close()
