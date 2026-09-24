#!/usr/bin/env python3
"""把一条灵感或 GitHub 选题写进本地 SQLite，并立即同步飞书。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import feishu_sync
import selection_db


def main() -> int:
    ap = argparse.ArgumentParser(description="写入播客选题")
    ap.add_argument("--title")
    ap.add_argument("--kind", choices=["idea", "project"])
    ap.add_argument("--project")
    ap.add_argument("--url")
    ap.add_argument("--summary")
    ap.add_argument("--why")
    ap.add_argument("--status")
    ap.add_argument("--source")
    ap.add_argument("--no-sync", action="store_true")
    args = ap.parse_args()

    data: dict[str, Any] = {}
    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            data = json.loads(raw)

    aliases = {
        "title": args.title or data.get("title") or data.get("标题"),
        "kind": args.kind or data.get("kind") or data.get("类型"),
        "project_full_name": args.project or data.get("project") or data.get("项目名"),
        "url": args.url or data.get("url") or data.get("链接"),
        "summary": args.summary or data.get("summary") or data.get("一句话说明"),
        "why": args.why or data.get("why") or data.get("为什么值得讲"),
        "status": args.status or data.get("status") or "inbox",
        "source": args.source or data.get("source") or "WorkBuddy",
    }
    if aliases["kind"] in ("灵感", "idea"):
        aliases["kind"] = "idea"
    elif aliases["kind"] in ("GitHub 项目", "GitHub项目", "project"):
        aliases["kind"] = "project"
    aliases = {k: v for k, v in aliases.items() if v is not None}
    row = selection_db.create_selection(aliases)
    result: dict[str, Any] = {"ok": True, "selection": row, "sync": None}
    if not args.no_sync:
        result["sync"] = feishu_sync.sync_once()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
