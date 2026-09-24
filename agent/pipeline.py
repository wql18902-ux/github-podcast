#!/usr/bin/env python3
"""外环：带状态的固定管线（设计稿 §4.1）。

为什么是「双环」而不是一个 agent 从头跑到尾（§2.1 的反例）：
写稿要 2-4 小时。会话跑到一半被平台收走 / 超时，**这一步的中间成果全部作废且无法续跑**，
而且不是「重跑一次就行」——已经读过的 8 个源码文件的上下文全丢了，得从头再读，积分双倍烧。

所以：
  外环（本文件）本机 Python 跑：调度、重试、断点续跑、闸门、降级、记账。确定性、可恢复、零模型成本。
  内环（宿主会话）只在 draft / review 两步消耗模型。

防跑飞三道保险（§4.1）：轮次上限、积分预算（只记账不硬拦）、每步超时。
"""

from __future__ import annotations

from typing import Any

from . import paths, stages, state, tools

# 硬循环上限：正常情况下 attempt 与 review_round 就把它兜住了，这里只防
# 「stage 互相指来指去」写成死循环。真撞上说明 next_stage 接线错了，要修代码。
_MAX_HOPS = 24

# 终态：跑到这些就没必要再往下
TERMINAL_STAGES = {"done", "prepare_failed", "draft_failed", "verify_failed", "handoff_failed", "no_audio"}


def run_episode(
    date: str,
    *,
    upto: str | None = None,
    from_stage: str | None = None,
    dry_run: bool = False,
    wait_host: bool = False,
    cfg: dict[str, Any] | None = None,
    conn=None,
    log=print,
) -> tuple[state.Episode | None, state.StageOutcome | None]:
    """从 episodes.stage 断点续跑，跑到 upto（含）为止。

    - upto=None  → 跑到需要宿主接手、或到终态为止
    - upto="verify" → 跑完 verify 就停（写稿那半截之后单独跑）
    - wait_host=True → draft / review 阻塞等 done.json（launchd 兜底或单进程跑）
    - dry_run=True  → 所有工具调用都不真执行（只走状态机，验证接线）

    返回 (期次记录, 最后一个阶段结果)。
    """
    cfg = cfg or paths.load_config()
    own_conn = conn is None
    conn = conn or state.connect()
    table = tools.load_tools()

    run_id = state.start_run(conn, date) if not dry_run else None
    ctx = stages.Context(
        conn=conn, date=date, cfg=cfg, table=table,
        dry_run=dry_run, run_id=run_id, wait_host=wait_host, log=log,
    )

    ep = state.current_episode(conn, date)
    stage = from_stage or (ep.stage if ep else "prepare")
    if stage in TERMINAL_STAGES:
        log(f"[=] {date} 已在终态 {stage}，无事可做")
        if own_conn:
            conn.close()
        return ep, None

    ctx.ep = ep
    log(f"===== 外环 {date} 从 {stage} 开始（dry_run={dry_run} wait_host={wait_host}）=====")

    last: state.StageOutcome | None = None
    hops = 0
    while hops < _MAX_HOPS:
        hops += 1
        ctx.refresh()
        log(f"\n--- [{stage}] ---")
        outcome = stages.run_stage(stage, ctx)
        last = outcome
        log(f"--- [{stage}] {'ok' if outcome.ok else 'fail'}：{outcome.detail}")

        if outcome.awaiting_host:
            log("\n[→] 交还宿主：会话按 agent/request.json 干活，干完写 agent/done.json，再跑 `python3 -m agent.cli resume`")
            break

        if stage == upto and outcome.ok:
            log(f"\n[=] 已跑到 {upto}，按要求停在这里")
            break

        nxt = outcome.next_stage
        if nxt is None:
            break
        if nxt.endswith("_failed") or nxt in TERMINAL_STAGES:
            stage = nxt
            break
        stage = nxt

    if hops >= _MAX_HOPS:
        log(f"[!] 循环超过 {_MAX_HOPS} 跳，强制停下（大概率是 next_stage 接线错了）")
        state.log_event(conn, date, "note", f"外环循环超过 {_MAX_HOPS} 跳被强制停下")

    ep = state.current_episode(conn, date)
    if run_id is not None:
        state.end_run(
            conn, run_id,
            exit_stage=stage,
            exit_reason=(last.detail[:500] if last else ""),
        )
    if own_conn:
        conn.close()
    return ep, last


def resume(date: str, **kw: Any) -> tuple[state.Episode | None, state.StageOutcome | None]:
    """宿主会话干完活之后的续跑入口：从库里记的 stage 继续（不是从 prepare 重来）。"""
    conn = kw.pop("conn", None) or state.connect()
    ep = state.current_episode(conn, date)
    if ep is None:
        raise SystemExit(f"库里没有 {date} 这一期，先跑 `python3 -m agent.cli run --date {date}`")
    return run_episode(date, conn=conn, **kw)
