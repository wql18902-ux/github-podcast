#!/usr/bin/env python3
"""命令行入口：run / resume / status / report / stage / events / doctor。

用法：
    python3 -m agent.cli status                    # 看今天这一期到哪了
    python3 -m agent.cli run --dry-run             # 不真跑，只走状态机验证接线
    python3 -m agent.cli run                       # 从断点跑到需要宿主接手
    python3 -m agent.cli resume                    # 宿主干完活之后续跑
    python3 -m agent.cli report                    # 一期体检报告
    python3 -m agent.cli fallback --date 2026-09-21  # 手动走降级合成（路线见 config/agent.json synth.fallback）
    python3 -m agent.cli doctor                    # 自检：接线、工具、红线

宿主无关（设计稿 §3.1）：这里只依赖标准库与 subprocess，任何 agent 跑它行为一致。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

from . import gates, paths, pipeline, stages, state, tools


def _today() -> str:
    return dt.date.today().isoformat()


# ---------------------------------------------------------------- status


def cmd_status(args) -> int:
    date = args.date or _today()
    conn = state.connect()
    ep = state.current_episode(conn, date)
    print(f"===== {date} =====")
    if ep is None:
        print("库里没有这一期。（`python3 -m agent.cli run` 会建）")
    else:
        print(f"期次   ep{ep.ep_no}")
        print(f"阶段   {ep.stage}")
        print(f"状态   {ep.status}" + (f"  ｜ 失败原因：{ep.fail_reason}" if ep.fail_reason else ""))
        print(f"仓库   {', '.join(ep.repos) or '（空）'}")
        print(f"写稿   尝试 {ep.attempt} 轮 ｜ 审稿回炉 {ep.review_round} 轮 ｜ 读文件 {ep.files_read or '未报'}")
        if ep.chars:
            print(f"正文   {ep.chars} 汉字 ≈{ep.est_minutes or 0:.0f} 分钟")
        if ep.audio_path:
            actual = f"{ep.actual_minutes:.1f} 分钟" if ep.actual_minutes else "时长未确认"
            print(f"音频   {ep.audio_path}（{actual}，路线 {ep.synth_route}）")

    pending = gates.pending_synthesis(paths.load_config())
    if pending["pending"]:
        print(f"待消费 上一期还没合成（{pending['age_h']}h 前落的稿），今天这轮会让路")

    open_run = state.open_run(conn, date)
    if open_run:
        print(f"未收尾 外环 run#{open_run['id']} 起于 {open_run['started_at']} 还没结束（可能被 kill）")

    evs = state.events(conn, date, limit=12)
    if evs:
        print("\n最近事件（倒序）：")
        for e in reversed(evs):
            print(f"  {e['ts'][11:19]} [{e['stage'] or '-'}] {e['event']}: {(e['detail'] or '')[:100]}")

    print(f"\n契约文件  {paths.rel(paths.LATEST_SCRIPT)} / {paths.rel(paths.LATEST_STATUS)}")
    if paths.LATEST_STATUS.exists():
        print("状态首行  " + paths.LATEST_STATUS.read_text(encoding="utf-8").splitlines()[0])
    conn.close()
    return 0


# ---------------------------------------------------------------- report


def cmd_report(args) -> int:
    date = args.date or _today()
    cfg = paths.load_config()
    conn = state.connect()
    print(gates.report(date, cfg, conn))
    conn.close()
    return 0


# ---------------------------------------------------------------- run / resume


def cmd_run(args) -> int:
    date = args.date or _today()
    ep, last = pipeline.run_episode(
        date,
        upto=args.upto,
        from_stage=args.from_stage,
        dry_run=args.dry_run,
        wait_host=args.wait_host,
    )
    return 0 if (last is None or last.ok) else 2


def cmd_resume(args) -> int:
    date = args.date or _today()
    ep, last = pipeline.resume(date, wait_host=args.wait_host, dry_run=args.dry_run)
    return 0 if (last is None or last.ok) else 2


def cmd_stage(args) -> int:
    """单跑一个阶段（排障用）。不推进 stage 指针的副作用由阶段自己负责。"""
    date = args.date or _today()
    cfg = paths.load_config()
    conn = state.connect()
    ctx = stages.Context(
        conn=conn, date=date, cfg=cfg, table=tools.load_tools(),
        dry_run=args.dry_run, wait_host=getattr(args, "wait_host", False), log=print,
    )
    ctx.ep = state.current_episode(conn, date)
    out = stages.run_stage(args.name, ctx)
    print(f"\n[{args.name}] ok={out.ok} next={out.next_stage} awaiting_host={out.awaiting_host}\n{out.detail}")
    if out.metrics:
        print(f"metrics: {out.metrics}")
    conn.close()
    return 0 if out.ok else 2


def cmd_fallback(args) -> int:
    return cmd_stage(argparse.Namespace(
        name="fallback", date=args.date, dry_run=args.dry_run, wait_host=False
    ))


def cmd_fallback_auto(args) -> int:
    """03:00 兜底班的入口（launchd 挂这个）。

    纯确定性、零模型成本——这正是它不该占 WorkBuddy 自动任务名额的原因（设计稿 §3）。

    行为：从 await_synth 续跑。于是两种结果都自然覆盖：
      - 豆包已经出了成品 → await_synth 立刻找到 → 进 publish（不重复合成）
      - 豆包没出 → await_synth 发现已过 synth_expect_by → 进 fallback →
        先查有没有成品、再过 pre_synth 三道闸（状态 OK / 稿子在 / 稿子 ≤12h），
        都过了才真跑本地 VoxCPM2。
    """
    date = args.date or _today()
    cfg = paths.load_config()
    conn = state.connect()
    ep = state.current_episode(conn, date)
    if ep is None:
        # 外环今晚没建期（没跑 / 没跑到 prepare）。补一行，让「没有音频」这个失败也有地方落，
        # 不要因为「库里没记录」就静默退出。
        ep = state.ensure_episode(conn, date, [], model=cfg["models"]["drafting"])
        print(f"[建期] 外环今晚没建期，补一行 ep{ep.ep_no} 给兜底班用")
    if ep.stage in pipeline.TERMINAL_STAGES:
        print(f"[=] {date} 已在终态 {ep.stage}，兜底班无事可做")
        conn.close()
        return 0
    ep, last = pipeline.run_episode(
        date, from_stage="await_synth", cfg=cfg, conn=conn, wait_host=False
    )
    conn.close()
    return 0 if (last is None or last.ok) else 2


def cmd_events(args) -> int:
    date = args.date or _today()
    conn = state.connect()
    evs = state.events(conn, date, limit=args.limit)
    for e in evs:
        print(f"{e['ts']}  [{e['stage'] or '-':12s}] {e['event']:22s} {(e['detail'] or '')[:160]}")
    print(f"\n共 {len(evs)} 条")
    conn.close()
    return 0


# ---------------------------------------------------------------- doctor


def cmd_doctor(args) -> int:
    """自检。设计稿 §12.3 第 1 步「这一步零风险，纯新增」的现场核实就是它。"""
    ok = True
    print("===== agent doctor =====")

    # 1) 平台无关红线（§3.1）：agent/ 不许 import 任何平台 SDK
    banned = re.compile(r"^\s*(import|from)\s+(anthropic|openai|codex|hermes|doubao|volcengine)\b", re.M)
    offenders = []
    for py in Path(__file__).resolve().parent.glob("*.py"):
        if banned.search(py.read_text(encoding="utf-8")):
            offenders.append(py.name)
    print(("✓" if not offenders else "✗") + f" 平台无关红线（agent/ 不许 import 平台 SDK）" + (f" 违规：{offenders}" if offenders else ""))
    ok &= not offenders

    # 2) 配置文件
    cfg = paths.load_config()
    print("✓ 配置 config/agent.json 可读（version {}）".format(cfg.get("version")))
    table = tools.load_tools()
    print(f"✓ 工具表 config/tools.json：{len(table)} 个  " + "、".join(sorted(table)))

    # 3) 工具命令在不在 PATH
    for name in ("prep", "verify", "push_script", "notify"):
        exists = tools.available(name)
        print(("✓" if exists else "!") + f" 命令可达：{name}")
        ok &= exists

    # 4) 数据库三张表
    conn = state.connect()
    have = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
    need = {"episodes", "episode_events", "agent_runs"}
    missing = need - have
    print(("✓" if not missing else "✗") + f" 状态表：{sorted(need)}" + (f" 缺 {sorted(missing)}" if missing else ""))
    ok &= not missing
    print(f"✓ 下一期期号：ep{state.next_ep_no(conn)}")

    # 5) 契约文件（§1.1 第一条不可动约束）
    print(("✓" if paths.LATEST_SCRIPT.exists() else "!") + f" 合约文件：{paths.rel(paths.LATEST_SCRIPT)}")
    if paths.LATEST_STATUS.exists():
        first = paths.LATEST_STATUS.read_text(encoding="utf-8").splitlines()[0]
        print(f"✓ {paths.rel(paths.LATEST_STATUS)} 首行：{first[:70]}")

    # 6) 黑名单这条闸是不是真开着（2026-09-21 修过一次「一次都没拦住」的 bug）
    cfg_bl = gates.blacklist_entries(cfg)
    print(("✓" if cfg_bl else "✗") + f" 黑名单可解析：{len(cfg_bl)} 条 → {cfg_bl}")
    ok &= bool(cfg_bl)

    conn.close()
    print("\n" + ("全部通过" if ok else "有项目没通过，见上面 ✗ / !"))
    return 0 if ok else 1


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m agent.cli", description="播客 Agent 外环")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_common(p, with_dry=True):
        p.add_argument("--date", default=None, help="YYYY-MM-DD，默认今天")
        if with_dry:
            p.add_argument("--dry-run", action="store_true", help="不真跑工具，只走状态机")

    p = sub.add_parser("run", help="从断点跑到需要宿主接手/或到终态")
    add_common(p)
    p.add_argument("--upto", default=None, choices=stages.STAGES, help="跑到这个阶段为止（含）")
    p.add_argument("--from", dest="from_stage", default=None, choices=stages.STAGES, help="强制从这个阶段开始")
    p.add_argument("--wait-host", action="store_true", help="draft/review 阻塞等 done.json（launchd 兜底用）")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("resume", help="宿主干完活之后续跑（从库里记的 stage 继续）")
    p.add_argument("--date", default=None)
    p.add_argument("--wait-host", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="不真跑工具，只走状态机")
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("status", help="这一期到哪了")
    p.add_argument("--date", default=None)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("report", help="一期体检报告")
    p.add_argument("--date", default=None)
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("stage", help="单跑一个阶段（排障）")
    add_common(p)
    p.add_argument("name", choices=stages.STAGES)
    p.add_argument("--wait-host", action="store_true")
    p.set_defaults(func=cmd_stage)

    p = sub.add_parser("fallback", help="走降级合成（synth.fallback 配的那条：本地 VoxCPM2 或 MiMo 克隆）")
    add_common(p)
    p.set_defaults(func=cmd_fallback)

    p = sub.add_parser("fallback-auto", help="03:00 兜底班的入口（launchd 挂这个，纯确定性零积分）")
    p.add_argument("--date", default=None)
    p.set_defaults(func=cmd_fallback_auto)

    p = sub.add_parser("events", help="看这一期的事件流水")
    p.add_argument("--date", default=None)
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_events)

    p = sub.add_parser("doctor", help="自检接线")
    p.set_defaults(func=cmd_doctor)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
