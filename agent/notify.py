#!/usr/bin/env python3
"""告警通道：把一段人话推给伟谦自己的飞书。

用法（也作为 config/tools.json 里的 `notify` 工具被调）：

    python3 -m agent.notify --text "第 2026-09-22 期写稿失败：latest-script.md 没被更新"
    python3 -m agent.notify --title "播客告警" --text "..." --key ep16-draft-failed

为什么不用 scripts/selection_push.py（设计稿 §4.2 原来推荐的那条）：
那个脚本的行为是「先写本地选题库，再同步飞书」——拿它当告警通道，
会在选题库里堆出一行行假选题。告警和选题是两件事，别共用一个写入口。

出口只有一条：lark-cli im 发给自己。失败**只返回非零**，绝不抛异常穿透——
告警发不出去不该把整期搞挂（tools.json 里这个工具的 on_fail 也是 continue）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# 本机 shell 的 http_proxy 指向 127.0.0.1:7890，代理进程经常不在，
# 联网 CLI 会报 Connection refused。项目里所有联网调用都显式剥掉这几个变量。
_PROXY_VARS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")

# lark-cli 装在 ~/.npm-global/bin，cron / launchd 的 PATH 里没有
_BIN_DIRS = [Path.home() / ".npm-global" / "bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin")]


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _PROXY_VARS}
    existing = [str(p) for p in _BIN_DIRS if p.is_dir()]
    env["PATH"] = os.pathsep.join(existing + [env.get("PATH", "")])
    return env


def _run(argv: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            argv, capture_output=True, text=True, errors="replace", timeout=timeout, env=_env()
        )
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError as exc:
        return 127, "", f"命令不存在：{exc}"
    except subprocess.TimeoutExpired:
        return -1, "", f"超时（{timeout}s）"


def self_open_id() -> str | None:
    code, out, _err = _run(["lark-cli", "contact", "+get-user"])
    if code != 0:
        return None
    try:
        data = json.loads(out)
    except ValueError:
        return None
    # 不同版本包法不一样，两处都试一下，取到就走
    for path in (("data", "user", "open_id"), ("data", "open_id"), ("open_id",)):
        cur = data
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                cur = None
                break
            cur = cur[key]
        if isinstance(cur, str) and cur.startswith("ou_"):
            return cur
    return None


def send(text: str, *, title: str = "", key: str | None = None, dry_run: bool = False) -> int:
    msg = f"【{title}】\n{text}" if title else text
    if dry_run:
        print(f"[dry-run] 会发给自己：\n{msg}")
        return 0

    uid = self_open_id()
    if not uid:
        print("取不到自己的 open_id（lark-cli contact +get-user 失败或登录态失效）", file=sys.stderr)
        return 1

    argv = ["lark-cli", "im", "+messages-send", "--user-id", uid, "--text", msg]
    if key:
        # lark-cli 的 idempotency-key 上限 50 字符，超了会被拒
        argv += ["--idempotency-key", key[:50]]
    code, out, err = _run(argv)
    if code != 0:
        print(f"发飞书失败：exit={code}\n{err.strip()[:500]}", file=sys.stderr)
        return 1
    print("已推飞书")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="播客告警推飞书")
    ap.add_argument("--text", required=True, help="正文（人话，直接能读懂）")
    ap.add_argument("--title", default="播客告警")
    ap.add_argument("--key", default=None, help="幂等键，防同一条告警发两遍")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return send(args.text, title=args.title, key=args.key, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
