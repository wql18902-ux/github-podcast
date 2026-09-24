#!/usr/bin/env python3
"""状态层：episodes / episode_events / agent_runs 的全部读写。

设计稿 §6.1 要求「全部读写都走这里，别处不直接连库」。两个理由：
  1. 状态变化必须顺带记事件（§9 的「S 写入 ← L 拦截」），散着写一定会有人漏；
  2. 期次状态是唯一真相源，一旦有第二条写入路径，就会出现「文件说 OK、库里说 failed」。
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from . import paths

SCHEMA = Path(__file__).resolve().parent / "schema.sql"

# set_metrics 允许改的列白名单。故意不给 stage —— 改阶段只能走 advance()，
# 因为它要连带写事件（§9）。
_METRIC_COLS = {
    "status",
    "repos",
    "script_path",
    "breakdown_path",
    "audio_path",
    "chars",
    "value_lines",
    "est_minutes",
    "actual_minutes",
    "attempt",
    "synth_route",
    "model",
    "fail_reason",
    "review_round",
    "files_read",
}


def now() -> str:
    """本地时区的 ISO 秒级时间戳，跟 selection_db.now() 同一格式（库里的时间要能互相比）。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """开库：WAL + Row 工厂，并保证三张表存在。

    默认路径是项目根的 info_source.db（设计稿 §3：复用 workbench 已经在读的那个库）。
    """
    p = Path(db_path) if db_path else paths.DB_PATH
    conn = sqlite3.connect(str(p), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn


# ---------------------------------------------------------------- 运行时结构


@dataclass
class Episode:
    """设计稿 §7.2。字段与 episodes 表一一对应，多出来的两个见 schema.sql 的注释。"""

    ep_no: int
    date: str
    stage: str
    status: str
    repos: list[str] = field(default_factory=list)
    script_path: str | None = None
    breakdown_path: str | None = None
    audio_path: str | None = None
    chars: int | None = None
    value_lines: int | None = None
    est_minutes: float | None = None
    actual_minutes: float | None = None
    attempt: int = 0
    synth_route: str | None = None
    model: str | None = None
    fail_reason: str | None = None
    review_round: int = 0
    files_read: int | None = None
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Episode":
        d = dict(row)
        raw = d.get("repos")
        repos: list[str] = []
        if raw:
            try:
                repos = list(json.loads(raw))
            except (TypeError, ValueError):
                # 容错：早年手写过的行可能是逗号分隔
                repos = [s.strip() for s in str(raw).split(",") if s.strip()]
        d["repos"] = repos
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class StageOutcome:
    """设计稿 §7.2。next_stage=None 表示这条流水线到此为止。

    awaiting_host 是实现时加的一个标记，不在设计稿里：
    外环**不能**自己调用模型，所以 draft / review 两个阶段跑完就交还控制权，
    让宿主会话（WorkBuddy / Claude Code / 任何 agent）去干，干完再 resume。
    没有这个标记，pipeline 会以为「这步失败了」而开始重试烧额度。
    """

    stage: str
    ok: bool
    next_stage: str | None
    retryable: bool = False
    detail: str = ""
    awaiting_host: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------- 期次读写


def current_episode(conn: sqlite3.Connection, date: str) -> Episode | None:
    row = conn.execute("select * from episodes where date = ?", (date,)).fetchone()
    return Episode.from_row(row) if row else None


def episode_by_no(conn: sqlite3.Connection, ep_no: int) -> Episode | None:
    row = conn.execute("select * from episodes where ep_no = ?", (ep_no,)).fetchone()
    return Episode.from_row(row) if row else None


def next_ep_no(conn: sqlite3.Connection) -> int:
    """下一期期号。

    设计稿 §6.1 原话是「首次从 output/episodes.log 行数回填」——**这条是错的，别照抄**：
    episodes.log 一行一个**仓库**（还有 `topic:xxx` 这种），到 2026-09-21 是 37 行，
    而真实期号是 15。拿行数当期号，会一次跳掉二十多期。
    真实回填源是 output/episodes/ep<N>-<slug>/ 目录名（workbench 也认它）。
    """
    row = conn.execute("select max(ep_no) as n from episodes").fetchone()
    db_max = int(row["n"] or 0)
    dir_max = 0
    if paths.EPISODES_DIR.is_dir():
        for child in paths.EPISODES_DIR.iterdir():
            m = re.match(r"ep(\d+)-", child.name)
            if m:
                dir_max = max(dir_max, int(m.group(1)))
    return max(db_max, dir_max) + 1


def create_episode(
    conn: sqlite3.Connection,
    date: str,
    repos: Iterable[str] = (),
    *,
    ep_no: int | None = None,
    model: str | None = None,
) -> Episode:
    ep_no = ep_no or next_ep_no(conn)
    ts = now()
    conn.execute(
        """insert into episodes
           (ep_no, date, stage, status, repos, attempt, review_round, model, created_at, updated_at)
           values (?, ?, 'prepare', 'running', ?, 0, 0, ?, ?, ?)""",
        (ep_no, date, json.dumps(list(repos), ensure_ascii=False), model, ts, ts),
    )
    conn.commit()
    log_event(conn, date, "note", f"建期 ep{ep_no}，仓：{', '.join(repos) or '（待选料）'}", stage="prepare")
    ep = current_episode(conn, date)
    assert ep is not None
    return ep


def ensure_episode(conn: sqlite3.Connection, date: str, repos: Iterable[str] = (), **kw: Any) -> Episode:
    """有就取、没有就建。断点续跑时重入的就是这条路径。"""
    ep = current_episode(conn, date)
    if ep:
        return ep
    return create_episode(conn, date, repos, **kw)


def advance(conn: sqlite3.Connection, date: str, stage: str, detail: str = "") -> None:
    """推进阶段。**唯一**允许改 episodes.stage 的入口，因为它顺带写事件（§9）。"""
    conn.execute(
        "update episodes set stage = ?, updated_at = ? where date = ?",
        (stage, now(), date),
    )
    conn.commit()
    log_event(conn, date, "stage_ok", detail or f"→ {stage}", stage=stage)


def fail(conn: sqlite3.Connection, date: str, reason: str, *, status: str = "failed", stage: str | None = None) -> None:
    conn.execute(
        "update episodes set status = ?, fail_reason = ?, updated_at = ? where date = ?",
        (status, reason, now(), date),
    )
    conn.commit()
    log_event(conn, date, "stage_fail", reason, stage=stage)


def set_metrics(conn: sqlite3.Connection, date: str, **fields: Any) -> None:
    """白名单式更新。写不认识的列名直接抛错，防手滑把状态写歪。"""
    unknown = set(fields) - _METRIC_COLS
    if unknown:
        raise KeyError(f"set_metrics 不认这些列：{sorted(unknown)}（要加列请同时改 schema.sql 与白名单）")
    if "repos" in fields and not isinstance(fields["repos"], str):
        fields["repos"] = json.dumps(list(fields["repos"]), ensure_ascii=False)
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"update episodes set {sets}, updated_at = ? where date = ?",
        (*fields.values(), now(), date),
    )
    conn.commit()


def bump_attempt(conn: sqlite3.Connection, date: str) -> int:
    """写稿尝试轮数 +1，返回新值。重试次数与断点位置必须同源（§9），
    所以 attempt 存库而不是存在调用栈里。"""
    conn.execute("update episodes set attempt = attempt + 1, updated_at = ? where date = ?", (now(), date))
    conn.commit()
    row = conn.execute("select attempt from episodes where date = ?", (date,)).fetchone()
    return int(row["attempt"]) if row else 0


def bump_review_round(conn: sqlite3.Connection, date: str) -> int:
    conn.execute("update episodes set review_round = review_round + 1, updated_at = ? where date = ?", (now(), date))
    conn.commit()
    row = conn.execute("select review_round from episodes where date = ?", (date,)).fetchone()
    return int(row["review_round"]) if row else 0


def log_event(
    conn: sqlite3.Connection,
    date: str,
    event: str,
    detail: str = "",
    *,
    stage: str | None = None,
) -> None:
    """只追加。永远不要把这里改成 upsert。"""
    conn.execute(
        "insert into episode_events (date, ts, stage, event, detail) values (?, ?, ?, ?, ?)",
        (date, now(), stage, event, detail),
    )
    conn.commit()


def events(conn: sqlite3.Connection, date: str, limit: int = 200) -> list[dict[str, Any]]:
    rows = conn.execute(
        "select * from episode_events where date = ? order by id limit ?", (date, limit)
    ).fetchall()
    return [dict(r) for r in rows]


def has_event(conn: sqlite3.Connection, date: str, event: str, *, stage: str | None = None) -> bool:
    """幂等闸用：某类操作这期是不是已经成功过（§9 的「T 可写 ← L 审批」）。"""
    if stage:
        row = conn.execute(
            "select 1 from episode_events where date = ? and event = ? and stage = ? limit 1",
            (date, event, stage),
        ).fetchone()
    else:
        row = conn.execute(
            "select 1 from episode_events where date = ? and event = ? limit 1", (date, event)
        ).fetchone()
    return row is not None


def recent_episodes(conn: sqlite3.Connection, limit: int = 8) -> list[Episode]:
    rows = conn.execute("select * from episodes order by date desc limit ?", (limit,)).fetchall()
    return [Episode.from_row(r) for r in rows]


def previous_episode(conn: sqlite3.Connection, date: str) -> Episode | None:
    row = conn.execute("select * from episodes where date < ? order by date desc limit 1", (date,)).fetchone()
    return Episode.from_row(row) if row else None


def previous_episode_script(date: str) -> str | None:
    """上一期稿子的路径（审稿要比对「有没有复述上一期讲过的内容」）。

    从 output/ 下按日期倒序找，不查库——审稿可能在工作台没起、库没建的情况下单跑，
    少一个依赖少一处失败点。找不到返回 None（审稿那一项就跳过，不判死）。
    """
    if not paths.OUTPUT_DIR.is_dir():
        return None
    prevs = sorted(
        (p for p in paths.OUTPUT_DIR.glob("????-??-??-script.md") if p.stem[:10] < date),
        reverse=True,
    )
    return paths.rel(prevs[0]) if prevs else None


# ---------------------------------------------------------------- 外环运行记录


def start_run(conn: sqlite3.Connection, date: str) -> int:
    cur = conn.execute(
        "insert into agent_runs (date, started_at) values (?, ?)", (date, now())
    )
    conn.commit()
    return int(cur.lastrowid)


def end_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    exit_stage: str = "",
    exit_reason: str = "",
    model_calls: int = 0,
    est_tokens: int = 0,
) -> None:
    conn.execute(
        """update agent_runs
           set ended_at = ?, exit_stage = ?, exit_reason = ?, model_calls = ?, est_tokens = ?
           where id = ?""",
        (now(), exit_stage, exit_reason, model_calls, est_tokens, run_id),
    )
    conn.commit()


def open_run(conn: sqlite3.Connection, date: str) -> dict[str, Any] | None:
    """有没有没收尾的那次运行（外环被 kill 时留下的）。cli status 会提示。"""
    row = conn.execute(
        "select * from agent_runs where date = ? and ended_at is null order by id desc limit 1",
        (date,),
    ).fetchone()
    return dict(row) if row else None
