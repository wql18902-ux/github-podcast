#!/usr/bin/env python3
"""过期复审：扫 episodes.log 里讲过的标的，查现况，给旧期次打「已被取代/停滞」提示。

每月 1 日跑一次（Hermes cron）。只读 + 写一份 output/stale-review-<YYYY-MM>.md，不改任何旧稿。

输出三列：期次 | 标的 | 现况提示
  - 「近 30 天有新版」→ ⚠️ 待跟（可能值得做一期「xx 换代了」）
  - 「近 180 天无动静」→ 💤 可能已停滞
  - 其余 → ✅ 无需动作
topic: 类标的（如 topic:AI-Agents(Claude-Code)）跳过自动查，标「需人工看 agent-map.md」。
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "output" / "episodes.log"
OUT_DIR = ROOT / "output"


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "stale-review"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def age_days(iso_ts):
    if not iso_ts:
        return None
    try:
        when = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return (datetime.now(timezone.utc) - when).days


def probe(full_name):
    """查一个仓库的现况：最新 release + push。"""
    info = {"release": None, "release_date": None, "push_days": None, "error": None}
    try:
        d = http_json(f"https://api.github.com/repos/{full_name}")
        info["push_days"] = age_days(d.get("pushed_at"))
    except Exception as e:
        info["error"] = f"仓库查询失败: {e}"
        return info
    try:
        r = http_json(f"https://api.github.com/repos/{full_name}/releases/latest")
        info["release"] = r.get("tag_name")
        info["release_date"] = (r.get("published_at") or "")[:10]
    except Exception:
        pass  # 没 release 不算错误
    return info


def verdict(info):
    if info["error"]:
        return f"❓ {info['error']}"
    rd = age_days((info["release_date"] or "") + "T00:00:00Z") if info["release_date"] else None
    if rd is not None and rd <= 30:
        return f"⚠️ 待跟：近 30 天有新版本 {info['release']}（{info['release_date']}）"
    if info["push_days"] is not None and info["push_days"] > 180:
        return f"💤 可能已停滞：近 {info['push_days']} 天无 push"
    rel = f"最新 {info['release']}（{info['release_date']}）" if info["release"] else "无 release"
    push = f"，近 {info['push_days']} 天有 push" if info["push_days"] is not None else ""
    return f"✅ 无需动作（{rel}{push}）"


def main():
    if not LOG_PATH.exists():
        print("[!] 没找到 episodes.log", file=sys.stderr)
        sys.exit(1)
    targets = [ln.strip() for ln in LOG_PATH.read_text().splitlines() if ln.strip()]

    month = datetime.now().strftime("%Y-%m")
    lines = [f"# 过期复审 · {month}", "",
             "> 自动跑，只读。扫 episodes.log 里讲过的标的，查现况。", ""]
    lines.append("| 期次 | 标的 | 现况提示 |")
    lines.append("|---|---|---|")
    for i, t in enumerate(targets, 1):
        if t.startswith("topic:"):
            lines.append(f"| {i} | `{t}` | ⏭ 非仓库标的，需人工看 [[agent-map]] |")
            continue
        info = probe(t)
        lines.append(f"| {i} | `{t}` | {verdict(info)} |")
    lines.append("")

    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"stale-review-{month}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[✓] 已写入 {out}")
    for ln in lines[5:]:
        if ln.startswith("|"):
            print("   ", ln)


if __name__ == "__main__":
    main()
