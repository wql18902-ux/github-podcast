#!/usr/bin/env python3
"""八个阶段的实现（设计稿 §4.1 的行为表）。

管线是**固定顺序的状态机**，不是自由 agent 编排：步骤之间严格顺序依赖
（没抓源就没法选料，没选料就没法读源码），无对抗、无协商（§12.1b）。

只有两个阶段的执行者不是本机：
  - `draft`（读源码写稿）与 `review`（独立审稿）交给**宿主会话**。
    外环不「调用」宿主，而是写 request.json 等 done.json（§4.1 结尾）。
    所以这两个阶段默认**立刻交还控制权**（awaiting_host），不是失败。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import gates, paths, request, state, tools

# 阶段顺序。返回 next_stage 时只能指向这张表里的名字（或 None / *_failed 终态）。
STAGES = ["prepare", "draft", "verify", "review", "handoff", "await_synth", "fallback", "publish"]


@dataclass
class Context:
    """一次外环运行的全部上下文。阶段函数只认它，不读全局。"""

    conn: Any
    date: str
    cfg: dict[str, Any]
    table: dict[str, tools.ToolSpec]
    dry_run: bool = False
    run_id: int | None = None
    wait_host: bool = False          # True = 阻塞等 host 干完（launchd 兜底或单进程跑）
    log: Callable[[str], None] = print
    ep: state.Episode | None = None

    @property
    def ep_no(self) -> int:
        return self.ep.ep_no if self.ep else 0

    def call(self, name: str, args: tuple = (), *, stage: str, env_extra=None) -> tools.ToolResult:
        return tools.call(
            self.table[name],
            args,
            conn=self.conn,
            date=self.date,
            stage=stage,
            env_extra=env_extra,
            dry_run=self.dry_run,
        )

    def refresh(self) -> None:
        self.ep = state.current_episode(self.conn, self.date)


def _out(stage: str, ok: bool, next_stage: str | None, detail: str = "", **kw: Any) -> state.StageOutcome:
    return state.StageOutcome(stage=stage, ok=ok, next_stage=next_stage, detail=detail, **kw)


def _episodes_log_lines() -> list[str]:
    if not paths.EPISODES_LOG.exists():
        return []
    return [
        ln.strip()
        for ln in paths.EPISODES_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        if ln.strip()
    ]


# ---------------------------------------------------------------- prepare


def prepare(ctx: Context) -> state.StageOutcome:
    """待消费闸 → fetch → 选料 → clone（设计稿 §4.1 的 prepare 行）。

    两个真实坑写进代码，别当异常排查：
      1. **准备脚本非零退出 ≠ 跳过本轮**（ep8 / ep13 / ep14 / ep15 连续四期）。
         sandbox 的 Path.mkdir 对已存在目录抛 EEXIST，把 clone 步打成非零退出，
         输出里**没有**「跳过本轮」字样。所以判据不是退出码，是「episodes.log 有没有新增」。
      2. **fetch 全失败必须 abort**，且不许覆盖旧稿。这条在脚本里已有闸门（'海外 0 个'）。
    """
    results = gates.pre_draft(ctx.date, ctx.cfg)
    for r in results:
        ctx.log(f"   [闸] {'✓' if r.passed else '–'} {r.name}: {r.detail}")

    d = gates.defer_requested(results)
    if d:
        # 让路但不写状态文件：豆包还要靠那个 OK 去合成待消费的旧稿。
        # 但要留一条事件——「今晚为什么没干活」必须查得到，不然复盘时只能猜。
        state.log_event(ctx.conn, ctx.date, "deferred", d.detail, stage="prepare")
        return _out("prepare", True, None, detail=d.detail, metrics={"deferred": True})

    bad = [r for r in results if not r.passed and r.hard]
    if bad:
        return _out("prepare", False, "prepare_failed", detail=gates.format_failure(results))

    before = _episodes_log_lines()
    res = ctx.call("prep", stage="prepare")
    ctx.log(f"   [工具] {res}")
    if not res.ok:
        ctx.log(f"   [工具] 退出码非 0（sandbox 的 EEXIST 是已知常态，先看有没有新增仓）\n{res.stdout_tail[-1500:]}")

    after = _episodes_log_lines()
    fresh = after[len(before):] if len(after) >= len(before) else []
    repos = [r for r in fresh if not r.startswith("topic:")] or fresh

    if ctx.dry_run:
        repos = repos or ["（dry-run 未真跑选料）"]

    if not repos:
        return _out(
            "prepare",
            False,
            "prepare_failed",
            detail="选料没产出任何仓库（episodes.log 没有新增行）。fetch 全失败或 clone 全挂，当日清单不可信，不许硬写。",
        )

    ctx.ep = state.ensure_episode(
        ctx.conn, ctx.date, repos, model=ctx.cfg["models"]["drafting"]
    )
    if ctx.ep.repos and ctx.ep.repos != repos:
        repos = ctx.ep.repos   # 续跑时以库里记的为准，别用这次 diff 覆盖
    else:
        state.set_metrics(ctx.conn, ctx.date, repos=repos)
    ctx.log(f"   [选料] ep{ctx.ep.ep_no} 仓库：{', '.join(repos)}")
    state.advance(ctx.conn, ctx.date, "draft", f"选料完成：{', '.join(repos)}")
    ctx.refresh()
    return _out("prepare", True, "draft", detail=f"选了 {len(repos)} 个仓", metrics={"repos": repos})


# ---------------------------------------------------------------- draft


def draft(ctx: Context) -> state.StageOutcome:
    """写稿：写 request.json，等宿主会话干活（设计稿 §4.1 的 draft 行）。"""
    if ctx.ep is None:
        return _out("draft", False, None, detail="没有期次记录，prepare 没跑成功")

    if ctx.ep.attempt >= ctx.cfg["budget"]["max_attempts_draft"]:
        state.fail(ctx.conn, ctx.date, f"写稿已试 {ctx.ep.attempt} 轮仍未过闸，按 max_attempts_draft 停机", stage="draft")
        return _out("draft", False, None, detail=f"写了 {ctx.ep.attempt} 轮都没过，不再硬跑（保留上一期旧稿）")

    request.clear_done()
    if ctx.dry_run:
        return _out(
            "draft", True, None, awaiting_host=True,
            detail="dry-run：不写 request.json，也不等回执（真实运行时这一步会交还宿主）",
        )
    rp = request.write_request(
        ctx.date, ep_no=ctx.ep.ep_no, task="draft", repos=ctx.ep.repos, cfg=ctx.cfg
    )
    ctx.log(f"   [契约] 已写 {paths.rel(rp)}，等宿主会话写稿")

    if not ctx.wait_host:
        return _out(
            "draft",
            True,
            None,
            awaiting_host=True,
            detail=(
                f"已请求写稿：{paths.rel(rp)}。宿主会话按 request.json 干完、把产物落盘、"
                f"再写 agent/done.json，然后跑 `python3 -m agent.cli resume` 继续。"
            ),
        )

    done = _wait_for_done(ctx, "draft", ctx.cfg["timeouts_s"]["draft"])
    return _judge_draft(ctx, done)


def _judge_draft(ctx: Context, done: dict[str, Any] | None) -> state.StageOutcome:
    if done is None:
        n = state.bump_attempt(ctx.conn, ctx.date)
        ctx.refresh()
        return _out(
            "draft",
            False,
            "draft",
            retryable=True,
            detail=f"等写稿超时，回执没到（第 {n} 轮）。下一轮会把闸门失败原因喂回去。",
        )

    status = str(done.get("status") or "")
    files_read = done.get("files_read")
    chars = done.get("chars")
    if files_read is None or chars is None:
        # 回执缺字段 = 会话没按契约写完。不当成 ok，退回重跑。
        n = state.bump_attempt(ctx.conn, ctx.date)
        ctx.refresh()
        return _out("draft", False, "draft", retryable=True, detail=f"回执缺 files_read/chars（第 {n} 轮），按未完成处理")

    state.set_metrics(
        ctx.conn, ctx.date, files_read=int(files_read), chars=int(chars),
        script_path=paths.rel(paths.LATEST_SCRIPT),
        breakdown_path=paths.rel(paths.date_paths(ctx.date)["breakdown"]),
    )

    min_files = ctx.cfg["budget"]["min_files_read"]
    if status != "ok":
        n = state.bump_attempt(ctx.conn, ctx.date)
        ctx.refresh()
        return _out("draft", False, "draft", retryable=True, detail=f"回执 status={status}（第 {n} 轮）")

    state.log_event(ctx.conn, ctx.date, "note", f"写稿回执：{files_read} 个文件 / {chars} 汉字", stage="draft")
    ctx.log(f"   [回执] 读了 {files_read} 个文件，{chars} 汉字")

    if int(files_read) < min_files:
        # 不拦，只提示（§4.3：可机械验的部分交给闸门，读得太浅提示一下）
        state.log_event(
            ctx.conn, ctx.date, "note",
            f"files_read={files_read} 低于 min_files_read={min_files}，读得偏浅（不拦，只提示）",
            stage="draft",
        )

    state.advance(ctx.conn, ctx.date, "verify", f"写稿完成：{chars} 汉字")
    ctx.refresh()
    return _out("draft", True, "verify", detail=f"{chars} 汉字", metrics={"chars": chars, "files_read": files_read})


def _wait_for_done(ctx: Context, task: str, timeout_s: int) -> dict[str, Any] | None:
    """阻塞等回执。只有 wait_host=True 才走这条路。"""
    interval = 20
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        done = request.read_done(ctx.date, task)
        if done is not None:
            return done
        time.sleep(interval)
    return None


# ---------------------------------------------------------------- verify


def verify(ctx: Context) -> state.StageOutcome:
    """跑闸门（设计稿 §4.1 的 verify 行 + §4.2 关于 verify-episode.sh 的处置）。

    这里**故意跑两遍**：Python 闸给结构化指标与持久化，verify-episode.sh 仍是
    「闸门唯一入口」、由它写 output/latest-status.txt（豆包那班读那个契约，格式一字不改）。

    为什么不只留一份：判据现在有两处实现（脚本里一套、config 里一套），短期内必然有
    细微差异。所以**以脚本的结论为准**（它是契约所有者），两者不一致时记一条 gate_drift
    事件——让漂移可见，而不是假装没有。等 §4.2 说的「薄包装」落地后，脚本内部读
    config，两处才真正合成一处。
    """
    results = gates.pre_synthesis(ctx.date, ctx.cfg)
    for r in results:
        ctx.log(f"   [闸] {'✓' if r.passed else ('–' if not r.hard else '✗')} {r.name}: {r.detail}")

    py_pass = gates.passed_all(results)
    res = ctx.call("verify", (ctx.date,), stage="verify")
    ctx.log(f"   [工具] {res}")

    if py_pass != res.ok:
        disagree = [r.name for r in results if r.hard and r.passed != res.ok]
        state.log_event(
            ctx.conn, ctx.date, "gate_drift",
            f"Python 闸判 {'过' if py_pass else '不过'}，verify-episode.sh 判 {'过' if res.ok else '不过'}；"
            f"以脚本为准（它是 latest-status.txt 的所有者）。可能不一致的硬闸："
            + ("、".join(disagree) if disagree else "（列表为空，属于提示类差异）"),
            stage="verify",
        )
        ctx.log("   [!] 两处闸门结论不一致，已记 gate_drift（以脚本为准）")

    metrics = gates.gate_metrics(results)
    state.set_metrics(
        ctx.conn, ctx.date,
        chars=metrics.get("chars"),
        value_lines=metrics.get("value_lines"),
        est_minutes=metrics.get("est_minutes"),
        script_path=paths.rel(paths.LATEST_SCRIPT),
        breakdown_path=paths.rel(paths.date_paths(ctx.date)["breakdown"]),
    )
    if metrics.get("short"):
        state.set_metrics(ctx.conn, ctx.date, status="short")

    if not res.ok:
        n = state.bump_attempt(ctx.conn, ctx.date)
        ctx.refresh()
        detail = gates.format_failure(results) or res.stdout_tail[-800:]
        if n >= ctx.cfg["budget"]["max_attempts_draft"]:
            state.fail(ctx.conn, ctx.date, f"闸门连续 {n} 轮没过：{res.stdout_tail[-200:]}", stage="verify")
            return _out("verify", False, None, detail=f"连续 {n} 轮没过闸，停机（保留上一期旧稿，不让豆包重录）")
        return _out("verify", False, "draft", retryable=True, detail=detail)

    nxt = "review" if ctx.cfg["review"]["enabled"] else "handoff"
    state.advance(ctx.conn, ctx.date, nxt, "过闸" + ("（进独立审稿）" if nxt == "review" else "（审稿关闭，直接交合成）"))
    ctx.refresh()
    return _out("verify", True, nxt, detail=f"过闸：{metrics.get('chars')} 汉字", metrics=metrics)


# ---------------------------------------------------------------- review


def review(ctx: Context) -> state.StageOutcome:
    """独立审稿（设计稿 §4.1 四条硬约束）。

    为什么排在 verify 后面：机械闸免费、快、判据确定；审稿 agent 要烧额度。
    先让便宜的把关，贵的后跑——稿子连字数/字段/密度都不够，不必浪费额度去审内容。
    """
    rcfg = ctx.cfg["review"]
    if not rcfg["enabled"]:
        state.advance(ctx.conn, ctx.date, "handoff", "审稿关闭")
        ctx.refresh()
        return _out("review", True, "handoff", detail="审稿环节已关闭")

    if ctx.ep and ctx.ep.review_round >= rcfg["max_rounds"]:
        state.advance(ctx.conn, ctx.date, "handoff", f"审稿已跑满 {rcfg['max_rounds']} 轮")
        ctx.refresh()
        return _out("review", True, "handoff", detail=f"审稿已跑满 {ctx.ep.review_round} 轮，不再回炉")

    request.clear_done()
    if ctx.dry_run:
        state.advance(ctx.conn, ctx.date, "handoff", "dry-run 跳过审稿")
        ctx.refresh()
        return _out("review", True, "handoff", detail="dry-run：不写审稿 request，直接往下")
    rp = request.write_request(ctx.date, ep_no=ctx.ep_no, task="review", cfg=ctx.cfg)
    ctx.log(f"   [契约] 已写 {paths.rel(rp)}（mode=review-only，allow_rewrite=false）")

    if not ctx.wait_host:
        return _out(
            "review",
            True,
            None,
            awaiting_host=True,
            detail=f"已请求审稿：{paths.rel(rp)}。宿主**必须新开会话**干这轮（复用 draft 会话 = 自己审自己）。",
        )

    done = _wait_for_done(ctx, "review", ctx.cfg["timeouts_s"]["review"])
    return _judge_review(ctx, done)


def _judge_review(ctx: Context, done: dict[str, Any] | None) -> state.StageOutcome:
    rcfg = ctx.cfg["review"]
    report = paths.date_paths(ctx.date)["review"]

    if done is None:
        state.log_event(ctx.conn, ctx.date, "note", "审稿超时/没回执，按「没审」处理，直接交合成", stage="review")
        state.advance(ctx.conn, ctx.date, "handoff", "审稿超时")
        ctx.refresh()
        return _out("review", True, "handoff", detail="审稿超时，不卡出稿（改稿不能把出稿卡死）")

    if str(done.get("status")) == "failed":
        state.log_event(ctx.conn, ctx.date, "note", f"审稿那轮失败：{done.get('notes') or ''}", stage="review")
        state.advance(ctx.conn, ctx.date, "handoff", "审稿失败但不停流程")
        ctx.refresh()
        return _out("review", True, "handoff", detail="审稿本身失败，流程继续（不能因为它卡住出稿）")

    _write_review_report(report, ctx.date, done)

    issues = request.read_review_issues(done, min_severity=rcfg["trigger_severity"])
    all_issues = done.get("issues") or []
    state.log_event(
        ctx.conn, ctx.date, "note",
        f"审稿：{done.get('issue_count', len(all_issues))} 个问题，其中达到 {rcfg['trigger_severity']} 的 {len(issues)} 个 → {paths.rel(report)}",
        stage="review",
    )

    if not issues:
        # medium 及以下只记录，不回炉
        state.advance(ctx.conn, ctx.date, "handoff", "审稿只报 medium 及以下")
        ctx.refresh()
        return _out("review", True, "handoff", detail=f"{len(all_issues)} 个问题但都不触发回炉", metrics={"issue_count": len(all_issues)})

    rnd = state.bump_review_round(ctx.conn, ctx.date)
    state.bump_attempt(ctx.conn, ctx.date)
    ctx.refresh()
    detail = "\n".join(f"- [{i.get('severity')}] {i.get('type')} @ {i.get('where')}：{i.get('problem')}" for i in issues)
    ctx.log(f"   [审稿] 发现 {len(issues)} 个高优先问题，回炉改一轮（第 {rnd} 轮，用掉一次 attempt）")
    return _out("review", False, "draft", retryable=True, detail=f"审稿发现 {len(issues)} 个 {rcfg['trigger_severity']} 问题，按下面改一轮：\n{detail}")


def _write_review_report(path: Path, date: str, done: dict[str, Any]) -> None:
    """审稿报告落盘。**宿主写了就不覆盖**——它那份带上下文，比这里拼的强。"""
    p = paths.abs_path(path)
    if p.exists():
        return
    issues = done.get("issues") or []
    lines = [
        f"# 审稿报告 · {date}",
        "",
        "> 独立会话产出。**只挑错，不重写**——稿子一个字都不由这一轮改（设计稿 §4.1）。",
        "",
        f"- 状态：{done.get('status')}",
        f"- 问题数：{done.get('issue_count', len(issues))}",
        f"- 模型：{done.get('model')}",
        "",
    ]
    if not issues:
        lines.append("没有报出问题。")
    for i in issues:
        lines += [
            f"## {i.get('id')}. [{i.get('severity')}] {i.get('type')}",
            "",
            f"- 位置：{i.get('where')}",
            f"- 原话：{i.get('quote')}",
            f"- 问题：{i.get('problem')}",
            f"- 依据：{i.get('rule')}",
            "",
        ]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- handoff


def handoff(ctx: Context) -> state.StageOutcome:
    """交棒给合成：校验契约 + 推稿子到飞书 + 补期次页（设计稿 §4.1 的 handoff 行）。"""
    # 1. 契约校验：这两个文件是豆包那班唯一看得见的东西，走之前必须确认在位、够新。
    problems: list[str] = []
    if not paths.LATEST_SCRIPT.exists():
        problems.append(f"没有 {paths.rel(paths.LATEST_SCRIPT)}")
    if not paths.LATEST_STATUS.exists():
        problems.append(f"没有 {paths.rel(paths.LATEST_STATUS)}")
    elif not paths.LATEST_STATUS.read_text(encoding="utf-8", errors="replace").startswith("OK"):
        problems.append(f"{paths.rel(paths.LATEST_STATUS)} 首行不是 OK（豆包会跳过，等于当夜没稿）")
    if problems:
        state.fail(ctx.conn, ctx.date, "；".join(problems), stage="handoff")
        return _out("handoff", False, None, detail="；".join(problems))

    # 2. 推讲稿到飞书。失败只记日志（on_fail=continue），不回退阶段——稿子本身已经验过了。
    res = ctx.call("push_script", ("--date", ctx.date), stage="handoff")
    ctx.log(f"   [工具] {res}")

    # 3. 期次页：缺 page.md = 这期在选题台上不存在（workbench 的机器可读声明只在 page.md 里）。
    #    只补一个**最小骨架**（机器可读行），内容留给人或写稿会话去长——这里不编故事。
    _ensure_page_stub(ctx)

    state.advance(ctx.conn, ctx.date, "await_synth", f"已交合成，期望 {ctx.cfg['schedule']['synth_expect_by']} 前出成品")
    ctx.refresh()
    return _out("handoff", True, "await_synth", detail="契约在位，稿子已推飞书")


def _ensure_page_stub(ctx: Context) -> None:
    eps_dir = paths.EPISODES_DIR
    if not eps_dir.is_dir():
        return
    # 找本期目录：优先 ep<N>-*，找不到就只提示（slug 不编）
    hits = sorted(eps_dir.glob(f"ep{ctx.ep_no}-*"))
    if not hits:
        ctx.log(f"   [!] 没有 output/episodes/ep{ctx.ep_no}-<slug>/ 目录——这期在选题台页面上会不存在，记得补 page.md")
        return
    page = hits[0] / "page.md"
    if page.exists():
        return
    ep = ctx.ep
    page.write_text(
        "\n".join(
            [
                f"# 第 {ctx.ep_no} 期 · {ctx.date}",
                "",
                f"- 上线：{ctx.date} 夜班落稿",
                *[f"- repo: {r}" for r in (ep.repos if ep else [])],
                f"- 稿子：`output/{ctx.date}-script.md`",
                f"- 拆解笔记：`output/{ctx.date}-breakdown.md`",
                "- 音频：待合成",
                "",
                "> 这是外环在 handoff 阶段补的**最小骨架**（只为让选题台认到这一期）。",
                "> 手写的那份 page.md 里有「这一期的骨头」「与选料简报的出入」，别用这份覆盖它。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    state.log_event(ctx.conn, ctx.date, "note", f"补了期次页骨架 {paths.rel(page)}", stage="handoff")


# ---------------------------------------------------------------- await_synth


def await_synth(ctx: Context) -> state.StageOutcome:
    """等豆包出成品（设计稿 §4.1 的 await_synth 行）。

    判据只用 mtime：产物比 latest-script.md 新就算出来了。**不许按文件名日期前缀判**
    （豆包产物叫「项目名-播客完整版-NNmin.m4a」，名字里没有日期）。
    """
    anchor = paths.LATEST_SCRIPT
    if not anchor.exists():
        return _out("await_synth", False, "fallback", detail="没有 latest-script.md，没什么可等的")

    # 复用幂等闸：如果本轮已经确认过豆包成品，直接过
    if state.has_event(ctx.conn, ctx.date, "tool_ok:push_script", stage="handoff"):
        pass  # 只是提醒：handoff 已经跑过，这里是续跑

    if ctx.dry_run:
        ctx.log("   [dry-run] 不真等豆包，直接判给 fallback 分支看流程")
        return _out("await_synth", True, "fallback", detail="dry-run：跳过等待")

    interval = int(ctx.cfg["synth"].get("poll_interval_s", 60))
    expect_by = _synth_deadline(ctx)
    ctx.log(f"   [等成品] 每 {interval}s 查一次 output/audio，等到 {expect_by:%H:%M} 还没就降级")

    while True:
        product = tools.newest_product(since=anchor)
        if product is not None:
            minutes = tools.probe_duration(product)
            state.set_metrics(
                ctx.conn, ctx.date,
                audio_path=paths.rel(product), actual_minutes=minutes, synth_route="doubao_app",
            )
            state.log_event(
                ctx.conn, ctx.date, "note",
                f"豆包出成品：{product.name}（{minutes:.1f} 分钟）" if minutes else f"豆包出成品：{product.name}",
                stage="await_synth",
            )
            ctx.log(f"   [成品] {product.name}")
            state.advance(ctx.conn, ctx.date, "publish", "豆包成品已到")
            ctx.refresh()
            return _out("await_synth", True, "publish", detail=f"成品 {product.name}")

        if time.time() >= expect_by.timestamp():
            state.log_event(
                ctx.conn, ctx.date, "degraded",
                f"到 {ctx.cfg['schedule']['synth_expect_by']} 还没有豆包成品，降级本地 VoxCPM2",
                stage="await_synth",
            )
            state.advance(ctx.conn, ctx.date, "fallback", "豆包超期")
            ctx.refresh()
            return _out("await_synth", False, "fallback", detail="豆包超期未出成品，走本地兜底")
        time.sleep(interval)


def _synth_deadline(ctx: Context):
    from datetime import datetime

    hh, mm = (int(x) for x in ctx.cfg["schedule"]["synth_expect_by"].split(":"))
    now = datetime.now()
    return now.replace(hour=hh, minute=mm, second=0, microsecond=0)


# ---------------------------------------------------------------- fallback


def fallback(ctx: Context) -> state.StageOutcome:
    """本地 VoxCPM2 兜底（设计稿 §4.1 的 fallback 行）。

    人工触发本步：`python3 -m agent.cli fallback --date YYYY-MM-DD`
    （正常路径是 await_synth 判超期后自动进来）。
    """
    results = gates.pre_synth(ctx.date, ctx.cfg)
    bad = [r for r in results if not r.passed]
    if bad:
        reason = "；".join(r.detail for r in bad)
        state.fail(ctx.conn, ctx.date, reason, status="no_audio", stage="fallback")
        _alert(ctx, "本期没法本地兜底", reason)
        return _out("fallback", False, None, detail=reason)

    out = paths.AUDIO_DIR / f"{ctx.date}-ep-local-fallback.m4a"

    # 先看是不是已经有成品了——**这一步是修 bug 加的**。
    # scripts/local-fallback.sh 第 39 行用 `ls output/audio/${TODAY}*.m4a` 判「今天有没有成品」，
    # 而豆包产物叫「项目名-播客完整版-NNmin.m4a」，名字里没有日期，所以那个判据**永远不成立**，
    # 豆包明明出了成品，本地兜底还是会白跑两小时 GPU。这里按 mtime 判（工具层同口径）。
    existing = tools.newest_product(since=paths.LATEST_SCRIPT)
    if existing is not None:
        minutes = tools.probe_duration(existing)
        state.set_metrics(
            ctx.conn, ctx.date,
            audio_path=paths.rel(existing), actual_minutes=minutes, synth_route="doubao_app",
        )
        state.log_event(
            ctx.conn, ctx.date, "note",
            f"已经有成品 {existing.name}，不需要本地兜底（按 mtime 判，不按文件名日期前缀）",
            stage="fallback",
        )
        ctx.log(f"   [跳过] 已有成品 {existing.name}，不用本地合成")
        state.advance(ctx.conn, ctx.date, "publish", "成品已在，跳过兜底")
        ctx.refresh()
        return _out("fallback", True, "publish", detail=f"已有成品 {existing.name}，跳过本地合成")

    attempts = sum(1 for e in state.events(ctx.conn, ctx.date) if e["event"] == "tool_fail:tts_local")
    if attempts >= ctx.cfg["budget"]["max_synth_attempts"]:
        reason = f"本地合成已失败 {attempts} 次（max_synth_attempts={ctx.cfg['budget']['max_synth_attempts']}），不再重试"
        state.fail(ctx.conn, ctx.date, reason, status="no_audio", stage="fallback")
        _alert(ctx, "本期没有音频", reason)
        return _out("fallback", False, None, detail=reason)

    res = ctx.call(
        "tts_local",
        (
            "--input", str(paths.LATEST_SCRIPT),
            "--output", str(out),
            "--denoise", ctx.cfg["synth"]["denoise"],
            # 刻意**不传 --voice-ref**：tts_local.py 会在默认位置
            # （voices/podcast-voice.wav）自动启用克隆模式，跟 scripts/local-fallback.sh
            # 那条已验证的调用保持一致。多传一个相对路径只是多一个失败点。
            # 不传参考音频会每段换人（见 voices/README.md），所以这依赖那个文件在位。
        ),
        stage="fallback",
    )
    ctx.log(f"   [工具] {res}")

    if not res.ok:
        state.log_event(ctx.conn, ctx.date, "degraded", f"本地合成失败（第 {attempts + 1} 次）", stage="fallback")
        if attempts + 1 >= ctx.cfg["budget"]["max_synth_attempts"]:
            state.fail(ctx.conn, ctx.date, "本地合成连续失败", status="no_audio", stage="fallback")
            _alert(ctx, "本期没有音频", f"本地 VoxCPM2 连续失败 {attempts + 1} 次，见 output/ 日志")
            return _out("fallback", False, None, detail="本地合成连续失败，判 no_audio")
        return _out("fallback", False, "fallback", retryable=True, detail="本地合成失败，还有一次机会")

    minutes = tools.probe_duration(out)
    state.set_metrics(
        ctx.conn, ctx.date,
        audio_path=paths.rel(out), actual_minutes=minutes, synth_route="local_voxcpm2",
    )
    state.advance(ctx.conn, ctx.date, "publish", "本地兜底合成完成")
    ctx.refresh()
    return _out("fallback", True, "publish", detail=f"本地合成完成 {paths.rel(out)}", metrics={"audio": paths.rel(out)})


# ---------------------------------------------------------------- publish


def publish(ctx: Context) -> state.StageOutcome:
    """上传 + 收尾（设计稿 §4.1 的 publish 行）。

    两条合成路线在「谁上传」上不一样，别搞混：
      - **豆包那条**自己会上传（docs/seed-audio-schedule.md 第 3 步），外环只做产物校验，
        **不重复传**——重复上传会在网易云云盘留两份同名文件。
      - **本地兜底那条**归外环上传（走 pipeline.sh upload-local，文件名带 -local 不撞名）。
    """
    ctx.refresh()
    if ctx.ep is None or not ctx.ep.audio_path:
        state.fail(ctx.conn, ctx.date, "没有音频产物，publish 无事可做", status="no_audio", stage="publish")
        return _out("publish", False, None, detail="没有 audio_path")

    audio = paths.abs_path(ctx.ep.audio_path)
    if ctx.dry_run:
        state.log_event(ctx.conn, ctx.date, "note", "dry-run：跳过产物校验与上传", stage="publish")
        state.set_metrics(ctx.conn, ctx.date, status=("short" if ctx.ep.status == "short" else "ok"))
        state.advance(ctx.conn, ctx.date, "done", "dry-run 收尾")
        ctx.refresh()
        return _out("publish", True, None, detail="dry-run：跳过上传，直接标 done")

    for r in gates.pre_upload(audio, ctx.cfg, est_minutes=ctx.ep.est_minutes):
        ctx.log(f"   [闸] {'✓' if r.passed else ('–' if not r.hard else '✗')} {r.name}: {r.detail}")
        if not r.passed and r.hard:
            state.fail(ctx.conn, ctx.date, f"产物不合格：{r.detail}", stage="publish")
            _alert(ctx, "产物不合格，没上传", r.detail)
            return _out("publish", False, None, detail=f"产物不合格：{r.detail}")

    if ctx.ep.synth_route == "doubao_app":
        state.log_event(
            ctx.conn, ctx.date, "note",
            "豆包那条线自己会上传网易云，外环不重复传（防云盘留两份同名文件）",
            stage="publish",
        )
        ctx.log("   [上传] 豆包路线，外环跳过（豆包自己传）")
    else:
        res = ctx.call("upload_local", (str(audio),), stage="publish")
        ctx.log(f"   [工具] {res}")
        if not res.ok:
            state.fail(ctx.conn, ctx.date, f"上传失败：{res.stderr_tail[-300:]}", stage="publish")
            _alert(ctx, "上传网易云失败", "登录态可能失效，需要你在电脑上重新登录 ncm-cli。不自动重试。")
            return _out("publish", False, None, detail="上传失败（登录态失效就不自动重试，推飞书等人）")

    status = "short" if ctx.ep.status == "short" else "ok"
    state.set_metrics(ctx.conn, ctx.date, status=status)
    state.advance(ctx.conn, ctx.date, "done", f"上线完成（{ctx.ep.synth_route}）")
    ctx.refresh()
    return _out("publish", True, None, detail=f"done，{status}")


def _alert(ctx: Context, title: str, text: str) -> None:
    """告警。on_fail=continue，发不出去也不改流程结论。

    幂等键用**稳定的**哈希（hashlib，不用内置 hash()）——内置 hash() 每个进程的种子不同，
    同一个 title 换一次运行就得到不同的键，等于没做幂等。
    """
    if not ctx.cfg["notify"]["feishu"]:
        return
    import hashlib

    key = hashlib.sha1(f"{ctx.date}:{title}".encode("utf-8")).hexdigest()[:40]
    ctx.call("notify", ("--title", title, "--text", f"[{ctx.date}] {text}", "--key", key), stage="notify")


# ---------------------------------------------------------------- 注册表 / 分发

DISPATCH: dict[str, Callable[[Context], state.StageOutcome]] = {
    "prepare": prepare,
    "draft": draft,
    "verify": verify,
    "review": review,
    "handoff": handoff,
    "await_synth": await_synth,
    "fallback": fallback,
    "publish": publish,
}


def run_stage(name: str, ctx: Context) -> state.StageOutcome:
    if name not in DISPATCH:
        raise KeyError(f"没有这个阶段：{name}（现有：{STAGES}）")
    state.log_event(ctx.conn, ctx.date, "stage_start", f"进入 {name}", stage=name)
    return DISPATCH[name](ctx)
