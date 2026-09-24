#!/usr/bin/env python3
"""工具层：把现有 CLI 脚本按 config/tools.json 声明的方式调起来。

设计稿 §4.2 的两条硬要求：
  - 固定管线 + 显式工具表。**不给模型自由 function-calling** —— 给固定管线配一个
    没人调用的工具注册表是过度设计。
  - 读写分离。writable=false 的工具外环永不重试写操作；writable=true 且
    idempotent=false 的，调用前先查 episode_events，同类操作这期成功过就跳过。

只碰 subprocess 与标准库。这里不许出现任何平台 SDK 的 import。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import paths, state

TOOLS_JSON = paths.CONFIG_DIR / "tools.json"

# cron / launchd / 各家 agent 的 PATH 都不一样，ncm-cli 与 lark-cli 装在
# ~/.npm-global/bin（pipeline.sh 里也补过同一件事）。这里补一次，免得
# 「手动跑得通、定时跑 command not found」。
_PATH_PREPEND = [
    Path.home() / ".npm-global" / "bin",
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
]


@dataclass
class ToolSpec:
    """设计稿 §7.2 / §4.2。字段名与 config/tools.json 一一对应，别改名。"""

    name: str
    cmd: list[str]
    timeout_s: int
    writable: bool
    idempotent: bool
    on_fail: str = "abort"          # abort | retry | degrade | continue
    env: dict[str, str] = field(default_factory=dict)
    desc: str = ""
    cwd: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ToolSpec":
        return cls(
            name=d["name"],
            cmd=list(d["cmd"]),
            timeout_s=int(d["timeout_s"]),
            writable=bool(d["writable"]),
            idempotent=bool(d["idempotent"]),
            on_fail=d.get("on_fail", "abort"),
            env={k: str(v) for k, v in (d.get("env") or {}).items()},
            desc=d.get("desc", ""),
            cwd=d.get("cwd"),
        )


@dataclass
class ToolResult:
    """设计稿 §6.2。stdout/stderr 各留末 2000 字符——够排查，不至于把日志撑爆。"""

    name: str
    ok: bool
    exit_code: int = 0
    stdout_tail: str = ""
    stderr_tail: str = ""
    duration_s: float = 0.0
    timed_out: bool = False
    skipped: bool = False        # 幂等闸拦下的，或 dry-run 没真跑
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    def __str__(self) -> str:
        if self.skipped:
            return f"{self.name}: SKIP（{self.reason}）"
        flag = "ok" if self.ok else "FAIL"
        extra = " 超时" if self.timed_out else ""
        return f"{self.name}: {flag} exit={self.exit_code} {self.duration_s:.1f}s{extra}"


def load_tools(path: str | Path | None = None) -> dict[str, ToolSpec]:
    p = Path(path) if path else TOOLS_JSON
    with open(p, encoding="utf-8") as fh:
        raw = json.load(fh)
    return {d["name"]: ToolSpec.from_dict(d) for d in raw["tools"]}


def _augmented_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    existing = [str(p) for p in _PATH_PREPEND if p.is_dir()]
    if existing:
        env["PATH"] = os.pathsep.join(existing + [env.get("PATH", "")])
    if extra:
        env.update(extra)
    return env


def _tail(text: str | None, n: int = 2000) -> str:
    if not text:
        return ""
    return text if len(text) <= n else "…（前略）" + text[-n:]


def call(
    spec: ToolSpec,
    args: Sequence[Any] = (),
    *,
    conn=None,
    date: str | None = None,
    stage: str | None = None,
    env_extra: dict[str, str] | None = None,
    dry_run: bool = False,
) -> ToolResult:
    """跑一个工具。

    conn + date 给了才会记事件与做幂等检查；不给就是「裸调」（调试用）。
    """
    argv = [*spec.cmd, *[str(a) for a in args]]
    cwd = spec.cwd or str(paths.PROJECT_ROOT)
    label = f"{stage}:{spec.name}" if stage else spec.name

    # ---- 幂等闸（§9「T 可写 ← L 审批」）----
    # 只在「有写、且重复调用不等价」时拦。拦的依据是「这期这个工具成功过」，
    # 而不是「跑过」——失败过的当然要能重试。
    if conn is not None and date and spec.writable and not spec.idempotent:
        if state.has_event(conn, date, f"tool_ok:{spec.name}"):
            res = ToolResult(
                name=spec.name,
                ok=True,
                skipped=True,
                reason=f"本期 {spec.name} 已成功过一次，不重复执行（幂等闸）",
            )
            state.log_event(conn, date, "note", f"跳过重复 {label}：{res.reason}", stage=stage)
            return res

    if dry_run:
        res = ToolResult(name=spec.name, ok=True, skipped=True, reason=f"dry-run，未执行：{' '.join(argv)}")
        return res

    t0 = time.monotonic()
    timed_out = False
    stdout = stderr = ""
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            env=_augmented_env({**spec.env, **(env_extra or {})}),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=spec.timeout_s,
        )
        exit_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = -1
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr if isinstance(exc.stderr, str) else "") + f"\n[超时] 超过 {spec.timeout_s}s 被外环杀掉"
    except FileNotFoundError as exc:
        exit_code = 127
        stderr = f"[命令不存在] {exc}\nPATH={os.environ.get('PATH', '')}"
    duration = time.monotonic() - t0

    res = ToolResult(
        name=spec.name,
        ok=(exit_code == 0 and not timed_out),
        exit_code=exit_code,
        stdout_tail=_tail(stdout),
        stderr_tail=_tail(stderr),
        duration_s=duration,
        timed_out=timed_out,
    )

    if conn is not None and date:
        # 事件落库：成功打 tool_ok:<name>（幂等闸认这个标记），失败打 tool_fail。
        event = f"tool_ok:{spec.name}" if res.ok else f"tool_fail:{spec.name}"
        detail = f"{' '.join(argv)} → exit={exit_code} {duration:.1f}s"
        if res.ok and spec.writable:
            state.log_event(conn, date, event, detail, stage=stage)
        elif not res.ok:
            state.log_event(conn, date, event, f"{detail}\n{res.stderr_tail[-800:]}", stage=stage)
    return res


def call_by_name(
    name: str,
    args: Sequence[Any] = (),
    *,
    tools: dict[str, ToolSpec] | None = None,
    **kw: Any,
) -> ToolResult:
    table = tools if tools is not None else load_tools()
    if name not in table:
        raise KeyError(f"config/tools.json 里没有这个工具：{name}（现有：{sorted(table)}）")
    return call(table[name], args, **kw)


def available(name: str) -> bool:
    """命令在不在 PATH。装在 ~/.npm-global/bin 的那几个（ncm-cli / lark-cli）容易缺。"""
    table = load_tools()
    spec = table.get(name)
    if not spec:
        return False
    return shutil.which(spec.cmd[0], path=_augmented_env()["PATH"]) is not None


def probe_duration(path: str | Path) -> float | None:
    """量音频实测时长（分钟）。只用 ffprobe，拿不到就返回 None——
    量不到不该拦整期，只该让报告里那一行写「未确认」。"""
    p = paths.abs_path(path)
    if not p.exists():
        return None
    res = call_by_name(
        "ffprobe",
        ["-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(p)],
    )
    if not res.ok:
        return None
    raw = res.stdout_tail.strip().splitlines()
    try:
        return float(raw[-1]) / 60.0
    except (ValueError, IndexError):
        return None


def newest_product(since: str | Path | None = None, exts: Iterable[str] = (".m4a", ".mp3")) -> Path | None:
    """output/audio 里最新一个成品。

    `since` 给了就只认比它新的——这是判「豆包出成品了没」的正确方式：
    **按 mtime，不按文件名日期前缀**。豆包产物叫「项目名-播客完整版-NNmin.m4a」，
    名字里没有日期，`ls output/audio/${TODAY}*` 那种写法永远匹配不到
    （scripts/local-fallback.sh 第 39 行就是踩了这个坑）。
    """
    if not paths.AUDIO_DIR.is_dir():
        return None
    anchor = paths.abs_path(since) if since else None
    anchor_mtime = anchor.stat().st_mtime if anchor and anchor.exists() else None
    cands = [
        p
        for p in paths.AUDIO_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in set(exts)
    ]
    if anchor_mtime is not None:
        cands = [p for p in cands if p.stat().st_mtime > anchor_mtime]
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)
