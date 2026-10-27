#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读扫描：把本机「Agent 的记忆/规则」分门别类列出来，供交接给别的宿主用。

不读内容、不复制、不上传；只出路径、体积、文件数、类型判断。
产物：_tmp/memory-inventory.md 与 _tmp/memory-inventory.json
"""
import json
import os
import subprocess
from pathlib import Path

HOME = Path.home()
OUT_MD = HOME / "ai-brain" / "github-podcast" / "_tmp" / "memory-inventory.md"
OUT_JSON = OUT_MD.with_suffix(".json")

# (标签, 路径, 类别, 说明)
TARGETS = [
    ("ai-brain 全局入口", HOME / "ai-brain" / "AGENTS.md", "身份/规则", "全局红线与入口，软链到 CLAUDE.md"),
    ("ai-brain 全局", HOME / "ai-brain" / "CLAUDE.md", "身份/规则", ""),
    ("ai-jarvis 记忆索引", HOME / "ai-brain" / "ai-jarvis" / "memory", "记忆", "MEMORY-INDEX.md 与沉淀下来的经验（真正的记忆索引）"),
    ("magpie 技能库", HOME / ".config" / "magpie" / "library" / "skills", "能力/技能", "~/.claude/skills 里的软链全指到这里"),
    ("ai-jarvis .agents 技能", HOME / "ai-brain" / "ai-jarvis" / ".agents" / "skills", "能力/技能", ""),
    ("ai-jarvis .claude 技能", HOME / "ai-brain" / "ai-jarvis" / ".claude" / "skills", "能力/技能", ""),
    ("ai-jarvis 内容库", HOME / "ai-brain" / "ai-jarvis" / "content", "记忆", "素材与逐字稿来源，体积大、按需迁"),
    ("飞轮系统", HOME / "ai-brain" / "flywheel-system.md", "记忆", "个人飞轮与长期判断"),
    ("Claude 全局规则", HOME / ".claude" / "CLAUDE.md", "身份/规则", ""),
    ("Claude 记忆", HOME / ".claude" / "memory", "记忆", ""),
    ("Claude 技能", HOME / ".claude" / "skills", "能力/技能", "skill 定义本身就是可迁移的资产"),
    ("Claude 会话流水", HOME / ".claude" / "projects", "会话流水", "可丢，仅作回溯；不建议迁移"),
    ("Codex 规则", HOME / ".codex" / "AGENTS.md", "身份/规则", ""),
    ("Codex 提示词", HOME / ".codex" / "prompts", "能力/技能", ""),
    ("Codex 会话流水", HOME / ".codex" / "sessions", "会话流水", "体积最大的噪音"),
    ("DSH 技能", HOME / ".dsh" / "skills", "能力/技能", ""),
    ("DSH 会话", HOME / ".dsh" / "sessions", "会话流水", ""),
    ("CodeBuddy 配置", HOME / ".codebuddy", "配置", "小，但含宿主级设置"),
    ("WorkBuddy 配置", HOME / ".workbuddy", "配置", ""),
    ("Cursor 规则", HOME / ".cursor" / "rules", "身份/规则", ""),
]

PROJECT_MARKERS = ["AGENTS.md", "CLAUDE.md", "MEMORY.md", ".cursorrules", "GEMINI.md"]
PROJECT_MEM_DIRS = ["memory", "记忆", "memories", ".memory"]
SKIP = {"node_modules", ".git", ".venv", "venv", "__pycache__", "dist", "build", "cache", ".cache",
        "_trash", "_归档", "Library", ".Trash"}


def du(path: Path):
    """软链要跟到真实目标，否则 AGENTS.md / skills 这类全报 0B。"""
    try:
        real = path.resolve() if path.is_symlink() else path
        out = subprocess.run(["du", "-sk", str(real)], capture_output=True, text=True)
        return int(out.stdout.split()[0]) * 1024
    except Exception:
        return 0


def count_files(path: Path, limit=20000):
    n = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP]
        n += len(files)
        if n > limit:
            return limit
    return n


def human(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def scan_projects(root=HOME, max_depth=4):
    rows = []
    root_depth = len(root.parts)
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        depth = len(Path(dirpath).parts) - root_depth
        if depth > max_depth:
            dirs[:] = []
            continue
        hit = [f for f in files if f in PROJECT_MARKERS]
        memdirs = [d for d in dirs if d in PROJECT_MEM_DIRS]
        if hit:
            rows.append({
                "path": dirpath,
                "files": hit,
                "size": du(Path(dirpath) / hit[0]),
            })
        for d in memdirs:
            p = Path(dirpath) / d
            rows.append({"path": str(p), "files": ["（记忆目录）"], "size": du(p)})
    return rows


def main():
    rows = []
    for label, path, kind, note in TARGETS:
        exists = path.exists()
        rows.append({
            "label": label,
            "path": str(path).replace(str(HOME), "~"),
            "kind": kind,
            "note": note,
            "exists": exists,
            "size": du(path) if exists else 0,
            "files": count_files(path) if exists and path.is_dir() else (1 if exists else 0),
        })
    projects = scan_projects()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"global": rows, "projects": projects}, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    lines = ["# 本机 Agent 记忆落点清单", "",
             f"> 只读扫描 · 生成于 {__import__('datetime').date.today()} · 不读内容、不上传", "",
             "## 一、宿主级（跨项目）", "",
             "| 标签 | 类别 | 体积 | 文件数 | 路径 |", "| --- | --- | ---: | ---: | --- |"]
    for r in rows:
        mark = "" if r["exists"] else "（不存在）"
        lines.append(f"| {r['label']}{mark} | {r['kind']} | {human(r['size'])} | {r['files']} | `{r['path']}` |")

    by_kind = {}
    for r in rows:
        by_kind.setdefault(r["kind"], 0)
        by_kind[r["kind"]] += r["size"]
    lines += ["", "### 按类别合计", "", "| 类别 | 合计体积 | 迁移建议 |", "| --- | ---: | --- |"]
    advice = {"身份/规则": "必迁：这是「你是谁」", "记忆": "必迁：这是「你经历过什么」",
              "能力/技能": "必迁：可复用的能力", "配置": "看情况：含宿主私有设置",
              "会话流水": "不建议：体积大、可丢"}
    for k, v in sorted(by_kind.items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {human(v)} | {advice.get(k, '')} |")

    lines += ["", "## 二、项目级（每个项目自己的规则/记忆）", "",
              f"共 {len(projects)} 处。", "",
              "| 路径 | 命中文件 | 体积 |", "| --- | --- | ---: |"]
    for p in projects:
        lines.append(f"| `{p['path'].replace(str(HOME), '~')}` | {', '.join(p['files'])} | {human(p['size'])} |")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD}  ({len(rows)} 个宿主级落点 / {len(projects)} 个项目级落点)")
    for r in rows:
        if r["exists"] and r["kind"] in ("身份/规则", "记忆"):
            print(f"  {r['kind']:6s} {human(r['size']):>8s} {r['path']}")


if __name__ == "__main__":
    main()
