#!/usr/bin/env python3
"""本地选题台 —— 项目、稿件、选题和 Claude 任务的浏览服务。

把散在各处的东西聚成一个能翻的页面：
  - 候选池：info_source.db 里 fetch.py 抓到的开源项目
  - 已讲：output/episodes/*/page.md 的期次页 + 拆解稿 + 成稿 + 音频
  - 稿件索引：output/ 下所有 md

约定：
  - 只绑定 127.0.0.1（默认 8788），不对外
  - 选题和任务只写入 info_source.db 新增表；不提供删除接口
  - Claude CLI 只做选题分析，不写稿、不改项目文件
  - 服务端把 markdown 渲染成 HTML，前端零外部依赖（不吃 CDN，离线可用）

跑法：python3 scripts/workbench_server.py [--port 8788]
"""

from __future__ import annotations

import argparse
import html as _esc
import json
import mimetypes
import os
import re
import socket
import sqlite3
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = PROJECT_ROOT / "web"
OUTPUT_DIR = PROJECT_ROOT / "output"
EPISODE_DIR = OUTPUT_DIR / "episodes"
RESEARCH_DIR = OUTPUT_DIR / "research"
AUDIO_DIR = OUTPUT_DIR / "audio"
TTS_CONSOLE_DIR = OUTPUT_DIR / "tts-console"
VOICE_REF = PROJECT_ROOT / "voices" / "podcast-voice.wav"
LOCAL_TTS_HOST = "127.0.0.1"
LOCAL_TTS_PORT = 8083
TTS_TEST_MAX_CHARS = 200
DB_PATH = Path(os.environ.get("GITHUB_PODCAST_DB", PROJECT_ROOT / "info_source.db"))
CACHE_DIR = PROJECT_ROOT / "cache"
TOPIC_LIBRARY = PROJECT_ROOT / "选题库.md"
WEEKDAY_ZH = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

import claude_select
import weekly_select
import cloud_tts
import feishu_sync
import selection_db

ALLOWED_SUFFIXES = {".md", ".txt", ".json", ".m4a", ".mp3", ".wav", ".png", ".jpg", ".jpeg", ".html"}

STOP_EVENT = threading.Event()
SYNC_LOCK = threading.Lock()
LAST_SYNC = {"ok": True, "at": "", "result": None, "error": ""}
LAST_SCRIPT_PUSH = {"ok": True, "at": "", "result": None, "error": ""}


# ---------------------------------------------------------------- 工具

def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _cjk_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except Exception:
        return 0


def _ticks(text: str) -> list[str]:
    return re.findall(r"`([^`]+)`", text)


def _field(text: str, label: str) -> str:
    """从期次页里取一个 `- 标签：值` 字段。"""
    pat = re.compile(r"^[ \t]*[-*]?[ \t]*\**\s*" + re.escape(label) + r"\s*\**\s*[:：]\s*(.+)$", re.M)
    m = pat.search(text)
    return m.group(1).strip() if m else ""


def _doc_meta(path: Path) -> dict[str, Any]:
    text = _read_text(path)
    title = ""
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return {
        "path": _rel(path),
        "name": path.name,
        "title": title or path.stem,
        "chars": _cjk_count(text),
        "size": _size(path),
        "mtime": _mtime(path),
    }


# ---------------------------------------------------------------- markdown 渲染

_INLINE_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")


def _inline(text: str) -> str:
    s = _esc.escape(text, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
    s = _INLINE_LINK.sub(
        lambda m: '<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (m.group(2), m.group(1)),
        s,
    )
    s = _WIKILINK.sub(lambda m: '<a class="wl" data-wl="%s">%s</a>' % (m.group(1), m.group(1)), s)
    return s


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_table_sep(line: str) -> bool:
    s = line.strip()
    if "-" not in s:
        return False
    return bool(re.fullmatch(r"\|?[\s:\-|]+\|?", s)) and set(s) <= set("-: |")


def _is_hr(line: str) -> bool:
    s = line.strip()
    return bool(re.fullmatch(r"(\*[ \t]*){3,}|(-[ \t]*){3,}|(_[ \t]*){3,}", s))


def _slug(text: str, used: dict[str, int]) -> str:
    base = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text).strip("-") or "h"
    n = used.get(base, 0)
    used[base] = n + 1
    return base if n == 0 else "%s-%d" % (base, n)


def md_to_html(text: str) -> tuple[str, list[dict[str, Any]]]:
    """够用的 markdown -> HTML。返回 (html, 目录)。"""
    lines = text.split("\n")
    out: list[str] = []
    toc: list[dict[str, Any]] = []
    used: dict[str, int] = {}
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # 代码块
        if line.lstrip().startswith("```"):
            i += 1
            buf: list[str] = []
            while i < n and not lines[i].lstrip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append('<pre class="code"><code>%s</code></pre>' % _esc.escape("\n".join(buf)))
            continue

        # 空行
        if not line.strip():
            i += 1
            continue

        # 分隔线
        if _is_hr(line):
            out.append("<hr>")
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            text_ = m.group(2).strip()
            hid = _slug(text_, used)
            toc.append({"level": level, "text": text_, "id": hid})
            out.append('<h%d id="%s">%s</h%d>' % (level, hid, _inline(text_), level))
            i += 1
            continue

        # 表格
        if "|" in line and i + 1 < n and "|" in lines[i + 1] and _is_table_sep(lines[i + 1]):
            head = _split_row(line)
            i += 2
            rows: list[list[str]] = []
            while i < n and lines[i].strip() and "|" in lines[i]:
                rows.append(_split_row(lines[i]))
                i += 1
            t = ['<table><thead><tr>']
            t += ["<th>%s</th>" % _inline(c) for c in head]
            t.append("</tr></thead><tbody>")
            for r in rows:
                r = (r + [""] * len(head))[: len(head)]
                t.append("<tr>" + "".join("<td>%s</td>" % _inline(c) for c in r) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue

        # 引用
        if line.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>%s</blockquote>" % "<br>".join(_inline(b) for b in buf))
            continue

        # 列表
        if re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
            items: list[tuple[int, bool, str]] = []
            while i < n:
                mm = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[i])
                if not mm:
                    break
                indent = len(mm.group(1).replace("\t", "  "))
                ordered = bool(re.match(r"\d", mm.group(2)))
                items.append((indent, ordered, mm.group(3)))
                i += 1
            buf = []
            depth = 0
            open_li = False
            for indent, ordered, txt in items:
                d = 0 if indent < 2 else 1
                while depth < d:
                    buf.append("<ul>")
                    depth += 1
                if open_li:
                    buf.append("</li>")
                    open_li = False
                while depth > d:
                    buf.append("</li></ul>")
                    depth -= 1
                buf.append("<li%s>%s" % (' class="d1"' if d else "", _inline(txt)))
                open_li = True
            if open_li:
                buf.append("</li>")
            while depth > 0:
                buf.append("</ul>")
                depth -= 1
            out.append("".join(buf))
            continue

        # 段落
        buf = []
        while i < n and lines[i].strip() and not re.match(r"^\s*(#{1,6}\s|>|([-*+]|\d+[.)])\s)", lines[i]) \
                and not lines[i].lstrip().startswith("```") and not _is_hr(lines[i]) \
                and not ("|" in lines[i] and i + 1 < n and "|" in lines[i + 1] and _is_table_sep(lines[i + 1])):
            buf.append(lines[i].strip())
            i += 1
        if buf:
            out.append("<p>%s</p>" % "<br>".join(_inline(b) for b in buf))

    return "\n".join(out), toc


# ---------------------------------------------------------------- 已讲项目

# 新期次优先在 page.md 里写声明行（`- repo: owner/repo`，一期多仓就写多行）；
# 这里只钉 ep1-9 的准确仓库地址作兜底，声明和字典都不用改老期次
EPISODE_REPOS: dict[str, dict[str, Any]] = {
    "ep1-whisper-cpp": {
        "repos": ["ggml-org/whisper.cpp"],
        "urls": ["https://github.com/ggml-org/whisper.cpp"],
        "note": "首期；音频未留存单独版本，稿子同时是全项目文稿口径样板",
    },
    "ep2-ecc": {
        "repos": ["affaan-m/ECC"],
        "urls": ["https://github.com/affaan-m/ECC"],
    },
    "ep3-hermes-agent": {
        "repos": ["NousResearch/hermes-agent"],
        "urls": ["https://github.com/NousResearch/hermes-agent"],
    },
    "ep4-n8n": {
        "repos": ["n8n-io/n8n"],
        "urls": ["https://github.com/n8n-io/n8n"],
    },
    "ep5-claude-code": {
        "repos": ["anthropics/claude-code"],
        "urls": ["https://github.com/anthropics/claude-code"],
        "note": "标的闭源（读的是打包产物字符串 + 官方博客）；拆解笔记已被第 6 期夜班覆盖丢失",
    },
    "ep6-autogpt": {
        "repos": ["Significant-Gravitas/AutoGPT"],
        "urls": ["https://github.com/Significant-Gravitas/AutoGPT"],
    },
    "ep7-codex-claude-code": {
        "repos": ["openai/codex", "anthropics/claude-code"],
        "urls": ["https://github.com/openai/codex", "https://github.com/anthropics/claude-code"],
        "note": "对比期；Codex 本机 clone 读源码，Claude Code 沿用第 5 期口径",
    },
    "ep8-memory-stack": {
        "repos": ["thedotmack/claude-mem", "MemPalace/mempalace", "Graphify-Labs/graphify"],
        "urls": [
            "https://github.com/thedotmack/claude-mem",
            "https://github.com/MemPalace/mempalace",
            "https://github.com/Graphify-Labs/graphify",
        ],
        "note": "记忆三件套拼盘；注意选料简报当日写的是 ollama，实际换题讲这三家（log 里 ollama 那行是「选中未讲」）",
    },
    "ep9-memory-ops": {
        "repos": ["mem0ai/mem0", "getzep/graphiti", "basicmachines-co/basic-memory"],
        "urls": [
            "https://github.com/mem0ai/mem0",
            "https://github.com/getzep/graphiti",
            "https://github.com/basicmachines-co/basic-memory",
        ],
        "note": "记忆存/取/忘三拼盘；选料脚本自动选了 open-webui 且 clone 超时失败，手动换题讲这三家（open-webui 未记账）；中途核验放弃 letta（main 分支已归档）",
    },
    "ep10-skills-portable": {
        "repos": ["nexu-io/open-design", "obra/superpowers", "anthropics/skills"],
        "urls": [
            "https://github.com/nexu-io/open-design",
            "https://github.com/obra/superpowers",
            "https://github.com/anthropics/skills",
        ],
        "note": "技能封装三拼盘（定形状/定纪律/做组装）；选题库点名 open-design；选料脚本自动选了 open-webui（off-theme，已记账未讲），手动换题讲这三家",
    },
}

# 产物兜底字典：page.md 声明行（- 稿子/拆解笔记/音频：`路径`）优先于这里；
# 老期次没写全声明时才落到这张表
EPISODE_ARTIFACTS: dict[str, dict[str, Any]] = {
    "ep1-whisper-cpp": {
        "breakdown": [],
        "script": ["output/podcast-01-whisper-cpp.md"],
        "audio": [],
    },
    "ep2-ecc": {
        "breakdown": ["output/episodes/ep2-ecc/breakdown.md"],
        "script": [
            "output/episodes/ep2-ecc/script.md",
            "output/episodes/ep2-ecc/完整稿-50min.md",
            "output/episodes/ep2-ecc/试水稿.md",
        ],
        "audio": ["output/audio/ecc-播客完整版-51min.m4a"],
    },
    "ep3-hermes-agent": {
        "breakdown": ["output/episodes/ep3-hermes-agent/brief.md"],
        "script": ["output/episodes/ep3-hermes-agent/script.md"],
        "audio": ["output/audio/hermes-播客完整版-114min.m4a"],
    },
    "ep4-n8n": {
        "breakdown": [],
        "script": ["output/episodes/ep4-n8n/script.md"],
        "audio": ["output/audio/n8n-播客完整版-60min.m4a"],
    },
    "ep5-claude-code": {
        "breakdown": [],
        "script": ["output/episodes/ep5-claude-code/script.md"],
        "audio": [
            "output/audio/agent-播客完整版-57min.m4a",
            "output/audio/2026-09-11-ep5-local.m4a",
            "output/audio/2026-09-11-ep5-local-test.m4a",
        ],
    },
    "ep6-autogpt": {
        "breakdown": ["output/2026-09-11-breakdown.md"],
        "script": ["output/2026-09-11-script.md"],
        "audio": [
            "output/audio/autogpt-播客完整版-38min.m4a",
            "output/audio/2026-09-12-ep-local-fallback.m4a",
        ],
    },
    "ep7-codex-claude-code": {
        "breakdown": ["output/2026-09-12-breakdown.md"],
        "script": ["output/2026-09-12-script.md"],
        "audio": [],
    },
    "ep8-memory-stack": {
        "breakdown": ["output/2026-09-14-breakdown.md"],
        "script": ["output/2026-09-14-script.md"],
        "audio": ["output/audio/memory-播客完整版-46min.m4a"],
    },
    "ep9-memory-ops": {
        "breakdown": ["output/2026-09-15-breakdown.md"],
        "script": ["output/2026-09-15-script.md"],
        "audio": [],
    },
    "ep10-skills-portable": {
        "breakdown": ["output/2026-09-16-breakdown.md"],
        "script": ["output/2026-09-16-script.md"],
        "audio": [],
    },
}

RESEARCH_ITEMS: list[dict[str, Any]] = [
    {
        "id": "research-2026-09-12-gemini-cli",
        "date": "2026-09-12",
        "repos": ["google-gemini/gemini-cli"],
        "urls": ["https://github.com/google-gemini/gemini-cli"],
        "script": "output/research/2026-09-12-gemini-cli.md",
        "breakdown": "output/research/breakdowns/2026-09-12-gemini-cli-breakdown.md",
        "audio": ["output/audio/2026-09-13-research-gemini-cli.m4a"],
        "note": "音频合成于 09-13，内容是本稿（注意：该项目已被官方接替，只作切面素材，不做现役拆解）",
    },
    {
        "id": "research-2026-09-13-agent-shells",
        "date": "2026-09-13",
        "repos": ["deepseek-ai/deepseek-harness", "OpenHands/OpenHands", "headroomlabs-ai/headroom"],
        "urls": [
            "https://github.com/deepseek-ai/deepseek-harness",
            "https://github.com/OpenHands/OpenHands",
            "https://github.com/headroomlabs-ai/headroom",
        ],
        "script": "output/research/2026-09-13-agent-shells.md",
        "breakdown": "output/research/breakdowns/2026-09-13-agent-shells-breakdown.md",
        "audio": [],
        "note": "三家拼盘：权限层 / 隔离层 / 预算层",
    },
]

CACHE_REPO_MAP = {
    "AutoGPT": "Significant-Gravitas/AutoGPT",
    "swe-bench": "SWE-bench/SWE-bench",
    "osworld": "xlang-ai/OSWorld",
    "swe-smith": "SWE-bench/SWE-smith",
    "ECC": "affaan-m/ECC",
    "anthropic-skills": "anthropics/skills",
    "basic-memory": "basicmachines-co/basic-memory",
    "buf": "bufbuild/buf",
    "claude-code-dump": "anthropics/claude-code",
    "claude-mem": "thedotmack/claude-mem",
    "codex": "openai/codex",
    "deepseek-harness": "deepseek-ai/deepseek-harness",
    "docling": "docling-project/docling",
    "cc-switch": "farion1231/cc-switch",
    "caveman": "JuliusBrussee/caveman",
    "langchain": "langchain-ai/langchain",
    "gemini-cli": "google-gemini/gemini-cli",
    "garak": "NVIDIA/garak",
    "gitleaks": "gitleaks/gitleaks",
    "graphify": "Graphify-Labs/graphify",
    "graphiti": "getzep/graphiti",
    "guardrails": "guardrails-ai/guardrails",
    "headroom": "headroomlabs-ai/headroom",
    "hermes-agent": "NousResearch/hermes-agent",
    "markitdown": "microsoft/markitdown",
    "mem0": "mem0ai/mem0",
    "mempalace": "MemPalace/mempalace",
    "n8n": "n8n-io/n8n",
    "ollama": "ollama/ollama",
    "open-design": "nexu-io/open-design",
    "openhands": "OpenHands/OpenHands",
    "ponytail": "DietrichGebert/ponytail",
    "promptfoo": "promptfoo/promptfoo",
    "ruff": "astral-sh/ruff",
    "safetensors": "safetensors/safetensors",
    "llama-cpp": "ggml-org/llama.cpp",
    "onnx": "onnx/onnx",
    "superpowers": "obra/superpowers",
    "trufflehog": "trufflesecurity/trufflehog",
}


_REPO_DECL = re.compile(r"^[ \t]*[-*][ \t]*\**\s*repo\**\s*[:：]\s*(\S+)", re.M)


def _norm_repo(value: str) -> str:
    """声明行抓到的仓库归一成 owner/repo（容忍反引号与完整 GitHub URL 写法）。"""
    s = value.strip().strip("`")
    if s.startswith("http"):
        s = re.sub(r"^https?://github\.com/", "", s).strip("/")
    return s


def _resolve_path(raw: str) -> str:
    """把页面手写的产物路径对到项目内真实存在的文件；不存在返回空（让位给字典/启发式）。"""
    s = raw.strip()
    if not s or s.startswith("http") or "/" not in s:
        return ""
    for cand in (s, "output/" + s.lstrip("./")):
        if (PROJECT_ROOT / cand).exists():
            return cand
    return ""


def _decl_path(text: str, label: str) -> str:
    """取 `- 标签：` 行里声明的产物路径。

    latest-script.md 这类滚动指针会换人，跳过不取（行里通常跟写着日期的归档件）；
    行内写「已丢失」这类叙述时不解析（ep5 的拆解笔记行，路径如今是别期的文件）。
    """
    value = _field(text, label)
    if not value or "已丢失" in value:
        return ""
    for t in _ticks(value):
        if re.search(r"/latest[^/]*$", t.strip()):
            continue
        c = _resolve_path(t)
        if c:
            return c
    return ""


def _date_heuristic_paths(date_line: str) -> dict[str, list[str]]:
    """第三级兜底：夜班按日期落盘，按「上线」日期试 output/<日期>-breakdown.md / -script.md。"""
    m = re.search(r"\d{4}-\d{2}-\d{2}", date_line or "")
    out: dict[str, list[str]] = {"breakdown": [], "script": []}
    if not m:
        return out
    date = m.group(0)
    for key, suffix in (("breakdown", "-breakdown.md"), ("script", "-script.md")):
        p = f"output/{date}{suffix}"
        if (PROJECT_ROOT / p).exists():
            out[key].append(p)
    return out


def _artifacts(paths: list[str]) -> list[dict[str, Any]]:
    out = []
    for p in paths:
        f = PROJECT_ROOT / p
        if f.exists():
            meta = _doc_meta(f)
            meta["kind"] = "brief" if "brief" in f.name.lower() else "breakdown"
            out.append(meta)
    return out


def _audio_items(paths: list[str]) -> list[dict[str, Any]]:
    out = []
    for p in paths:
        f = PROJECT_ROOT / p
        if f.exists():
            out.append({"path": _rel(f), "name": f.name, "size": _size(f), "mtime": _mtime(f)})
    return out


def collect_episodes() -> list[dict[str, Any]]:
    eps: list[dict[str, Any]] = []
    if not EPISODE_DIR.exists():
        return eps
    for d in sorted(EPISODE_DIR.iterdir()):
        if not d.is_dir():
            continue
        page = d / "page.md"
        if not page.exists():
            continue
        text = _read_text(page)
        m = re.match(r"ep(\d+)-(.+)$", d.name)
        no = int(m.group(1)) if m else 0
        first = next((l for l in text.splitlines() if l.startswith("# ")), "")
        title = first[2:].strip() if first else d.name
        title = re.sub(r"^第\s*\d+\s*期\s*[·:：]\s*", "", title)

        cutoff = _field(text, "信息截止")
        cutoff = cutoff.replace("**", "").strip()
        if "｜" in cutoff:
            cutoff = cutoff.split("｜")[0].strip()

        # 产物三级优先：page.md 声明 > 字典 > 按「上线」日期启发。新期次只需在 page.md 里写声明行
        meta = EPISODE_REPOS.get(d.name, {})
        art_entry = EPISODE_ARTIFACTS.get(d.name)
        art = art_entry if art_entry is not None else {"breakdown": [], "script": [], "audio": []}
        # 日期启发只兜字典不认识的新期次——老期次字典里的空列表是刻意记录（如 ep5 拆解已丢失），
        # 不能拿「上线日期撞上别期文件」的猜测去覆盖它
        heur = _date_heuristic_paths(_field(text, "上线")) if art_entry is None else {"breakdown": [], "script": []}
        script_decl = _decl_path(text, "稿子")
        breakdown_decl = _decl_path(text, "拆解笔记")
        audio_decl = _decl_path(text, "音频")
        script_paths = [script_decl] if script_decl else (art["script"] or heur["script"])
        breakdown_paths = [breakdown_decl] if breakdown_decl else (art["breakdown"] or heur["breakdown"])
        audio_paths = [audio_decl] if audio_decl else art["audio"]

        # 仓库两级优先：page.md 声明（一期多仓写多行 - repo:）> 字典；url 统一由 owner/repo 拼
        decl_repos = list(dict.fromkeys(
            r for r in (_norm_repo(v) for v in _REPO_DECL.findall(text)) if r
        ))
        if decl_repos:
            repos, repo_urls = decl_repos, [f"https://github.com/{r}" for r in decl_repos]
        else:
            repos, repo_urls = meta.get("repos", []), meta.get("urls", [])

        wl = [w for w in _WIKILINK.findall(text) if w != "agent-map"]
        eps.append({
            "id": d.name,
            "no": no,
            "title": title,
            "kind": "episode",
            "date_line": _field(text, "上线"),
            "topic_line": _field(text, "主题线"),
            "repo_line": _field(text, "标的"),
            "repos": repos,
            "repo_urls": repo_urls,
            "cutoff": cutoff,
            "note": meta.get("note", ""),
            "page": _rel(page),
            "breakdown": _artifacts(breakdown_paths),
            "scripts": _artifacts(script_paths),
            "audios": _audio_items(audio_paths),
            "wikilinks": wl,
            "has_breakdown": bool(breakdown_paths and _artifacts(breakdown_paths)),
        })
    return eps


def collect_research() -> list[dict[str, Any]]:
    out = []
    for item in RESEARCH_ITEMS:
        script = PROJECT_ROOT / item["script"]
        if not script.exists():
            continue
        meta = _doc_meta(script)
        bd = []
        if item.get("breakdown") and (PROJECT_ROOT / item["breakdown"]).exists():
            bd = [_doc_meta(PROJECT_ROOT / item["breakdown"])]
        out.append({
            "id": item["id"],
            "no": 0,
            "title": meta["title"],
            "kind": "research",
            "date": item["date"],
            "repos": item["repos"],
            "repo_urls": item["urls"],
            "cutoff": item["date"],
            "note": item.get("note", ""),
            "breakdown": bd,
            "scripts": [meta],
            "audios": _audio_items(item["audio"]),
            "wikilinks": [],
            "has_breakdown": bool(bd),
        })
    return out


def collect_candidates() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not DB_PATH.exists():
        return [], []
    told: dict[str, int] = {}
    for e in collect_episodes():
        for r in e["repos"]:
            told[r.lower()] = e["no"]
    for r in collect_research():
        for repo in r["repos"]:
            told.setdefault(repo.lower(), -1)

    cloned: dict[str, str] = {}
    if CACHE_DIR.exists():
        for d in CACHE_DIR.iterdir():
            if d.is_dir() and d.name in CACHE_REPO_MAP:
                cloned[CACHE_REPO_MAP[d.name].lower()] = d.name

    rows: list[dict[str, Any]] = []
    con = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True)
    con.row_factory = sqlite3.Row
    try:
        for r in con.execute(
            "select full_name, category, url, description, stars, language, topics, "
            "is_overseas, first_seen, last_seen from projects order by stars desc"
        ):
            key = (r["full_name"] or "").lower()
            try:
                topics = json.loads(r["topics"] or "[]")
            except Exception:
                topics = []
            rows.append({
                "full_name": r["full_name"],
                "category": r["category"] or "未分类",
                "url": r["url"] or ("https://github.com/%s" % r["full_name"]),
                "description": r["description"] or "",
                "stars": r["stars"] or 0,
                "language": r["language"] or "",
                "topics": topics[:8],
                "is_overseas": bool(r["is_overseas"]),
                "first_seen": r["first_seen"] or "",
                "last_seen": r["last_seen"] or "",
                "told_in": told.get(key),
                "cloned": cloned.get(key, ""),
                "cached": bool(cloned.get(key)),
            })
    finally:
        con.close()

    cats: dict[str, int] = {}
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    return rows, [{"name": k, "count": v} for k, v in sorted(cats.items(), key=lambda x: -x[1])]


def collect_selections() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = selection_db.list_selections(selection_db.DB_PATH, include_archived=True)
    states = selection_db.feishu_states(selection_db.DB_PATH)
    latest = selection_db.latest_task_by_selection(selection_db.DB_PATH)
    tasks = selection_db.list_tasks(selection_db.DB_PATH, limit=100)
    for row in rows:
        sid = int(row["id"])
        row["sync"] = states.get(sid, {})
        row["latest_task"] = latest.get(sid, {})
    return rows, tasks


def collect_docs() -> list[dict[str, Any]]:
    docs = []
    for f in sorted(OUTPUT_DIR.rglob("*.md")):
        if f.name == "README.md":
            continue
        meta = _doc_meta(f)
        p = meta["path"]
        low = f.name.lower()
        if "-breakdown" in low or "breakdown" in low or "/breakdown" in p:
            kind = "breakdown"
        elif "/research/" in p:
            kind = "research"
        elif "/episodes/" in p or "script" in low or "podcast-" in low:
            kind = "script"
        elif re.match(r"^\d{4}-\d{2}-\d{2}\.md$", f.name):
            kind = "daily"
        elif "brief" in low:
            kind = "brief"
        else:
            kind = "other"
        meta["kind"] = kind
        docs.append(meta)
    return docs


def build_overview() -> dict[str, Any]:
    episodes = collect_episodes()
    research = collect_research()
    candidates, categories = collect_candidates()
    docs = collect_docs()

    status = ""
    sf = OUTPUT_DIR / "latest-status.txt"
    if sf.exists():
        status = _read_text(sf).strip().splitlines()[0] if _read_text(sf).strip() else ""

    log_lines = []
    lf = OUTPUT_DIR / "episodes.log"
    if lf.exists():
        log_lines = [l.strip() for l in _read_text(lf).splitlines() if l.strip()]

    audios = []
    if AUDIO_DIR.exists():
        for f in sorted(AUDIO_DIR.iterdir()):
            if f.suffix.lower() in {".m4a", ".mp3", ".wav"}:
                audios.append({
                    "path": _rel(f), "name": f.name, "size": _size(f), "mtime": _mtime(f),
                })

    breakdowns_all = [d for d in docs if d["kind"] == "breakdown"]
    selections, selection_tasks = collect_selections()
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "root": str(PROJECT_ROOT),
        "stats": {
            "episodes": len(episodes),
            "research": len(research),
            "breakdowns": len(breakdowns_all),
            "scripts": len([d for d in docs if d["kind"] in ("script", "research")]),
            "docs": len(docs),
            "candidates": len(candidates),
            "told": len([c for c in candidates if c["told_in"] is not None]),
            "cloned": len([c for c in candidates if c["cached"]]),
            "audios": len(audios),
        },
        "status": status,
        "episodes_log": log_lines,
        "episodes": episodes,
        "research": research,
        "candidates": candidates,
        "categories": categories,
        "docs": docs,
        "audios": audios,
        "selections": selections,
        "selection_tasks": selection_tasks,
        "feishu": feishu_status(),
    }


def feishu_status() -> dict[str, Any]:
    cfg = feishu_sync.load_config()
    return {
        "configured": feishu_sync.is_configured(cfg),
        "base_token": cfg.get("base_token", ""),
        "table_id": cfg.get("table_id", ""),
        "table_name": cfg.get("table_name", ""),
        "views": cfg.get("views", []),
        "last_sync": dict(LAST_SYNC),
        "last_script_push": dict(LAST_SCRIPT_PUSH),
    }


def extract_plain_section(text: str) -> str:
    """取新拆解稿里的「人话导览」；旧稿返回空，前端显示原文。"""
    match = re.search(r"^## 人话导览\s*$([\s\S]*?)(?=^##\s|\Z)", text, re.M)
    return match.group(1).strip() if match else ""


# ---------------------------------------------------------------- 合成接入（TTS）

TTS_AUDIO_SUFFIXES = {".mp3", ".m4a", ".wav"}


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    """探活：能在 timeout 内建连即为 True，任何异常都当成没在跑。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def collect_tts_local() -> dict[str, Any]:
    """本地 VoxCPM2 引擎与音色参考的状态；探活限时，不允许长时间阻塞。"""
    running = _port_open(LOCAL_TTS_HOST, LOCAL_TTS_PORT)
    exists = VOICE_REF.exists()
    start_command = (
        "python3 scripts/tts_local.py "
        "--input output/latest-script.md "
        "--output /tmp/ep.m4a"
    )
    return {
        "engine": "VoxCPM2",
        "running": running,
        "host": LOCAL_TTS_HOST,
        "port": LOCAL_TTS_PORT,
        "address": "%s:%d" % (LOCAL_TTS_HOST, LOCAL_TTS_PORT),
        "voice_ref": _rel(VOICE_REF),
        "voice_ref_exists": exists,
        "denoise_default": "off",
        "denoise_options": ["off", "deesser", "deesser-treble"],
        "start_command": start_command,
    }


def collect_tts_audios(limit: int = 10) -> list[dict[str, Any]]:
    """output/tts-console/ 下最近的试听文件。"""
    if not TTS_CONSOLE_DIR.exists():
        return []
    files = [
        f
        for f in TTS_CONSOLE_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in TTS_AUDIO_SUFFIXES
    ]
    files.sort(key=_mtime_key, reverse=True)
    out = []
    for f in files[:limit]:
        out.append({"name": f.name, "mtime": _mtime(f), "size": _size(f)})
    return out


def _mtime_key(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _safe_tts_audio(raw: str) -> Path:
    """严格校验试听文件名：只在 output/tts-console/ 内、不越界。"""
    name = urllib.parse.unquote(raw or "").strip()
    if not name:
        raise ValueError("文件名为空")
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError("非法文件名")
    if name.startswith("."):
        raise ValueError("非法文件名")
    root = TTS_CONSOLE_DIR.resolve()
    target = (root / name).resolve()
    if target != root and root not in target.parents:
        raise ValueError("越界")
    if target.suffix.lower() not in TTS_AUDIO_SUFFIXES:
        raise ValueError("类型不允许")
    if not target.is_file():
        raise ValueError("文件不存在：%s" % name)
    return target


def _coerce_extra(value: Any) -> dict[str, Any]:
    """把前端传来的 extra 统一成 dict（允许 JSON 字符串）。"""
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("extra 不是合法 JSON：%s" % exc) from exc
        if not isinstance(parsed, dict):
            raise ValueError("extra 必须是 JSON 对象")
        return parsed
    raise ValueError("extra 必须是 JSON 对象")


def build_tts_state() -> dict[str, Any]:
    """合成接入面板的一份完整状态（不含任何密钥明文）。"""
    providers = cloud_tts.list_public_config()
    custom_ids = [pid for pid, item in providers.items() if item.get("custom")]
    return {
        "providers": providers,
        "adapters": cloud_tts.list_adapters(),
        "custom_ids": custom_ids,
        "local": collect_tts_local(),
        "audios": collect_tts_audios(),
    }


def tts_save_provider(body: dict[str, Any]) -> dict[str, Any]:
    """保存一个 provider 的配置与（可选）Key。"""
    provider = str(body.get("provider") or "").strip()
    if not provider:
        raise ValueError("缺少 provider")
    try:
        existing = cloud_tts.get_provider_config(provider)
    except cloud_tts.CloudTTSError:
        existing = {}

    def pick(field: str) -> str:
        value = body.get(field)
        if value is None:
            return str(existing.get(field) or "")
        return str(value)

    adapter = str(body.get("adapter") or existing.get("adapter") or "").strip()
    endpoint = pick("endpoint")
    model = pick("model")
    voice = pick("voice")
    extra = _coerce_extra(body.get("extra"))
    secret = body.get("secret")
    secret = str(secret) if secret else None
    clear_secret = bool(body.get("clear_secret"))
    label = body.get("label")

    cloud_tts.update_provider_config(
        provider,
        adapter=adapter,
        endpoint=endpoint,
        model=model,
        voice=voice,
        extra=extra,
        secret=secret,
        clear_secret=clear_secret,
        label=label if label is not None else None,
    )
    return build_tts_state()


def tts_create_provider(body: dict[str, Any]) -> dict[str, Any]:
    """新建自定义 provider，并在给了 Key 时写入 Keychain。"""
    pid = cloud_tts.create_custom_provider(
        body.get("id"),
        body.get("label"),
        str(body.get("adapter") or "").strip(),
        str(body.get("endpoint") or ""),
        str(body.get("model") or ""),
        str(body.get("voice") or ""),
        _coerce_extra(body.get("extra")),
    )
    secret = body.get("secret")
    if secret:
        cloud_tts.set_keychain_secret(pid, str(secret))
    return pid, build_tts_state()


def tts_delete_provider(body: dict[str, Any]) -> dict[str, Any]:
    provider = str(body.get("provider") or "").strip()
    if not provider:
        raise ValueError("缺少 provider")
    cloud_tts.delete_custom_provider(provider)
    return build_tts_state()


def tts_test(body: dict[str, Any]) -> dict[str, Any]:
    """试听：合成一段短文本到 output/tts-console/。"""
    provider = str(body.get("provider") or "").strip()
    if not provider:
        raise ValueError("缺少 provider")
    text = str(body.get("text") or "").strip()
    if not text:
        raise ValueError("文本为空")
    truncated = len(text) > TTS_TEST_MAX_CHARS
    if truncated:
        text = text[:TTS_TEST_MAX_CHARS]
    chars = len(text)

    TTS_CONSOLE_DIR.mkdir(parents=True, exist_ok=True)
    out = cloud_tts.synthesize(provider, text)
    name = out.name
    return {
        "ok": True,
        "name": name,
        "url": "/api/tts/audio?name=" + urllib.parse.quote(name),
        "chars": chars,
        "truncated": truncated,
    }


# ---------------------------------------------------------------- HTTP

def _safe_project_path(raw: str) -> Path:
    if not raw:
        raise ValueError("路径为空")
    p = (PROJECT_ROOT / urllib.parse.unquote(raw)).resolve()
    if p != PROJECT_ROOT and PROJECT_ROOT not in p.parents:
        raise ValueError("越界")
    if p.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError("类型不允许：%s" % p.suffix)
    return p


class Handler(BaseHTTPRequestHandler):
    server_version = "Workbench/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:  # 安静点
        pass

    def _json(self, payload: Any, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code: int, msg: str) -> None:
        self._json({"error": msg}, code)

    def _local_only(self) -> bool:
        return self.client_address[0] in {"127.0.0.1", "::1"}

    _ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}

    def _host_name(self, raw: str) -> str:
        """从 Host 头里取主机名部分（去端口），兼容 [::1]:8080 这种带方括号的形态。"""
        raw = (raw or "").strip().lower()
        if not raw:
            return ""
        if raw.startswith("["):
            end = raw.find("]")
            if end != -1:
                return raw[1:end].strip()
            return raw.strip("[]").strip()
        # 无方括号且含多个冒号：按 IPv6 字面量整体处理
        if raw.count(":") > 1:
            return raw
        return raw.split(":", 1)[0].strip()

    def _write_guard(self) -> str:
        """写请求（POST/PATCH）的前置防护，返回拒绝原因；空串表示放行。

        三层，抄自 tts_console._check_local_origin 的思路并加固：
          1) Host 白名单：堵 DNS rebinding —— 攻击者域名解析到 127.0.0.1 时，
             Origin 与 Host 会同源，单靠同源比对挡不住。
          2) Origin 同源（缺失则放行）：curl / 本地脚本不带 Origin。
          3) Sec-Fetch-Site: cross-site 一律拒绝。
        """
        host_raw = (self.headers.get("Host") or "").strip()
        if self._host_name(host_raw) not in self._ALLOWED_HOSTS:
            return "拒绝非本机 Host 的写请求"
        origin = (self.headers.get("Origin") or "").strip()
        if origin and origin not in ("http://%s" % host_raw, "https://%s" % host_raw):
            return "拒绝跨站来源的写请求"
        if (self.headers.get("Sec-Fetch-Site") or "").strip().lower() == "cross-site":
            return "拒绝跨站来源的写请求"
        return ""

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 1024 * 1024:
            raise ValueError("请求体为空或超过 1MB")
        raw = self.rfile.read(length).decode("utf-8")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return value

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        try:
            if not self._local_only():
                return self._err(HTTPStatus.FORBIDDEN, "只允许本机访问")
            guard = self._write_guard()
            if guard:
                return self._err(HTTPStatus.FORBIDDEN, guard)
            body = self._read_json()

            if route == "/api/selections":
                allowed = {
                    "title", "kind", "project_full_name", "url", "summary",
                    "why", "status", "priority", "source",
                }
                data = {k: body.get(k) for k in allowed if k in body}
                data.setdefault("source", "手动")
                row = selection_db.create_selection(data, selection_db.DB_PATH)
                return self._json({"ok": True, "selection": row}, HTTPStatus.CREATED)

            match = re.fullmatch(r"/api/selections/(\d+)/claude", route)
            if match:
                selection = selection_db.get_selection(int(match.group(1)), selection_db.DB_PATH)
                if not selection:
                    return self._err(HTTPStatus.NOT_FOUND, "选题不存在")
                task = selection_db.create_task(
                    int(selection["id"]), claude_select.build_prompt(selection), selection_db.DB_PATH
                )
                return self._json({"ok": True, "task": task}, HTTPStatus.CREATED)

            # 挪期：next_week = 排期日期顺延一周（没排过就从今天起算）并置 scheduled；
            # back = 撤回已选池、清掉排期日期
            match = re.fullmatch(r"/api/selections/(\d+)/postpone", route)
            if match:
                sel_id = int(match.group(1))
                selection = selection_db.get_selection(sel_id, selection_db.DB_PATH)
                if not selection:
                    return self._err(HTTPStatus.NOT_FOUND, "选题不存在")
                mode = (body.get("mode") or "next_week").strip()
                if mode == "back":
                    row = selection_db.update_selection(
                        sel_id, {"status": "shortlist", "scheduled_for": None}, selection_db.DB_PATH
                    )
                    return self._json({"ok": True, "selection": row})
                if mode != "next_week":
                    return self._err(HTTPStatus.BAD_REQUEST, "mode 只支持 next_week / back")
                base = selection.get("scheduled_for") or datetime.now().strftime("%Y-%m-%d")
                try:
                    shifted = (datetime.fromisoformat(base) + timedelta(days=7)).strftime("%Y-%m-%d")
                except ValueError:
                    return self._err(HTTPStatus.BAD_REQUEST, "已有排期日期不是合法 YYYY-MM-DD")
                row = selection_db.update_selection(
                    sel_id, {"status": "scheduled", "scheduled_for": shifted}, selection_db.DB_PATH
                )
                return self._json({"ok": True, "selection": row})

            if route == "/api/feishu/sync":
                if not feishu_sync.is_configured():
                    return self._err(HTTPStatus.CONFLICT, "飞书表还没配置，先运行 scripts/feishu_sync.py --setup")
                result = feishu_sync.sync_once(selection_db.DB_PATH)
                LAST_SYNC.update({
                    "ok": bool(result.get("ok")),
                    "at": selection_db.now(),
                    "result": result,
                    "error": "",
                })
                return self._json(result)

            # 手动推讲稿：force=True，稿子没变也重推（先删旧附件再传，不会堆积）
            if route == "/api/feishu/push-script":
                if not feishu_sync.is_configured():
                    return self._err(HTTPStatus.CONFLICT, "飞书表还没配置，先运行 scripts/feishu_sync.py --setup")
                date_str = str(body.get("date") or "").strip() or None
                result = feishu_sync.push_script(
                    selection_db.DB_PATH, date_str=date_str, force=True
                )
                LAST_SCRIPT_PUSH.update({
                    "ok": bool(result.get("ok")),
                    "at": selection_db.now(),
                    "result": result,
                    "error": "" if result.get("ok") else str(result.get("reason") or ""),
                })
                if not result.get("ok"):
                    return self._err(
                        HTTPStatus.CONFLICT, str(result.get("reason") or "讲稿推送失败")
                    )
                return self._json(result)
            # 周选题：建 plan+task 入队（同周已有排队/执行中的 proposed plan 则幂等复用）
            if route == "/api/weekly-tasks":
                week_raw = (body.get("week_start") or "").strip()
                if week_raw:
                    week = datetime.strptime(week_raw, "%Y-%m-%d").date()
                else:
                    week = weekly_select.next_monday()
                prompt = weekly_select.build_weekly_prompt(week, selection_db.DB_PATH)
                out = selection_db.create_weekly_plan(week.isoformat(), prompt, selection_db.DB_PATH)
                return self._json(
                    {"ok": True, **out},
                    HTTPStatus.OK if out["reused"] else HTTPStatus.CREATED,
                )

            # 确认落库：adopt = {日期: 是否采纳}；单事务失败回滚整批
            match = re.fullmatch(r"/api/weekly-plans/(\d+)/confirm", route)
            if match:
                adopt = body.get("adopt")
                if not isinstance(adopt, dict):
                    return self._err(HTTPStatus.BAD_REQUEST, "body 需要 adopt: {日期: 是否采纳}")
                results = selection_db.confirm_weekly_plan(
                    int(match.group(1)), {str(k): bool(v) for k, v in adopt.items()},
                    selection_db.DB_PATH,
                )
                # 排期真相源在库里，选题库.md 第 4 块回写镜像；失败不静默（照常落库，响应带原因）
                mirrored: Any = True
                try:
                    rebuild_topic_library_schedule(selection_db.DB_PATH)
                except Exception as exc:  # noqa: BLE001
                    mirrored = "%s: %s" % (type(exc).__name__, exc)
                    print("[workbench] 选题库第 4 块回写失败：%s" % mirrored)
                return self._json({"ok": True, "results": results, "topic_library_mirrored": mirrored})

            if route == "/api/tts/provider":
                state = tts_save_provider(body)
                return self._json({"ok": True, "state": state})

            if route == "/api/tts/provider/create":
                pid, state = tts_create_provider(body)
                return self._json(
                    {"ok": True, "provider": pid, "state": state},
                    HTTPStatus.CREATED,
                )

            if route == "/api/tts/provider/delete":
                state = tts_delete_provider(body)
                return self._json({"ok": True, "state": state})

            if route == "/api/tts/test":
                return self._json(tts_test(body))

            return self._err(HTTPStatus.NOT_FOUND, "未知路由：%s" % route)
        except cloud_tts.CloudTTSError as exc:
            return self._err(HTTPStatus.BAD_REQUEST, str(exc))
        except (ValueError, sqlite3.IntegrityError) as exc:
            return self._err(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._err(HTTPStatus.INTERNAL_SERVER_ERROR, "%s: %s" % (type(exc).__name__, exc))

    def do_PATCH(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        match = re.fullmatch(r"/api/selections/(\d+)", parsed.path)
        try:
            if not self._local_only():
                return self._err(HTTPStatus.FORBIDDEN, "只允许本机访问")
            guard = self._write_guard()
            if guard:
                return self._err(HTTPStatus.FORBIDDEN, guard)
            if not match:
                return self._err(HTTPStatus.NOT_FOUND, "未知路由：%s" % parsed.path)
            body = self._read_json()
            allowed = {"title", "summary", "why", "status", "priority", "url", "scheduled_for"}
            data = {k: body[k] for k in allowed if k in body}
            row = selection_db.update_selection(int(match.group(1)), data, selection_db.DB_PATH)
            return self._json({"ok": True, "selection": row})
        except (ValueError, sqlite3.IntegrityError) as exc:
            return self._err(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # noqa: BLE001
            return self._err(HTTPStatus.INTERNAL_SERVER_ERROR, "%s: %s" % (type(exc).__name__, exc))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        try:
            if route in ("/", "/index.html", "/workbench.html"):
                page = WEB_ROOT / "workbench.html"
                if not page.exists():
                    return self._err(500, "web/workbench.html 不存在")
                return self._bytes(page.read_bytes(), "text/html; charset=utf-8")

            if route == "/favicon.ico":
                return self._bytes(b"", "image/x-icon", 204)

            if route == "/api/overview":
                return self._json(build_overview())

            if route == "/api/doc":
                rel = (qs.get("rel") or [""])[0]
                p = _safe_project_path(rel)
                if not p.exists():
                    return self._err(404, "文件不存在：%s" % rel)
                text = _read_text(p)
                html, toc = md_to_html(text)
                plain_html, _ = md_to_html(extract_plain_section(text))
                return self._json({
                    "path": _rel(p),
                    "title": _doc_meta(p)["title"],
                    "chars": _cjk_count(text),
                    "mtime": _mtime(p),
                    "html": html,
                    "plain_html": plain_html,
                    "has_plain": bool(plain_html),
                    "toc": toc,
                })

            task_match = re.fullmatch(r"/api/tasks/(\d+)", route)
            if task_match:
                task = selection_db.get_task(int(task_match.group(1)), selection_db.DB_PATH)
                if not task:
                    return self._err(HTTPStatus.NOT_FOUND, "任务不存在")
                return self._json(task)

            weekly_task_match = re.fullmatch(r"/api/weekly-tasks/(\d+)", route)
            if weekly_task_match:
                task = selection_db.get_weekly_task(int(weekly_task_match.group(1)), selection_db.DB_PATH)
                if not task:
                    return self._err(HTTPStatus.NOT_FOUND, "周任务不存在")
                plan = selection_db.get_weekly_plan(int(task["plan_id"]), selection_db.DB_PATH)
                return self._json({"ok": True, "task": task, "plan": plan})

            if route == "/api/weekly-plans":
                return self._json({
                    "ok": True,
                    "plans": selection_db.latest_weekly_plans(selection_db.DB_PATH),
                })

            if route == "/media":
                rel = (qs.get("rel") or [""])[0]
                p = _safe_project_path(rel)
                if not p.exists():
                    return self._err(404, "文件不存在：%s" % rel)
                return self._serve_file(p)

            if route == "/api/tts/state":
                return self._json(build_tts_state())

            if route == "/api/tts/audio":
                name = (qs.get("name") or [""])[0]
                p = _safe_tts_audio(name)
                return self._serve_file(p)

            return self._err(404, "未知路由：%s" % route)
        except ValueError as exc:
            return self._err(400, str(exc))
        except BrokenPipeError:
            return
        except Exception as exc:  # noqa: BLE001
            return self._err(500, "%s: %s" % (type(exc).__name__, exc))

    def _serve_file(self, path: Path) -> None:
        total = _size(path)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        if not rng:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(total))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with path.open("rb") as fh:
                while True:
                    chunk = fh.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            return

        m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
        start = int(m.group(1)) if m and m.group(1) else 0
        end = int(m.group(2)) if m and m.group(2) else total - 1
        end = min(end, total - 1)
        length = max(0, end - start + 1)
        self.send_response(206)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, total))
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        with path.open("rb") as fh:
            fh.seek(start)
            remain = length
            while remain > 0:
                chunk = fh.read(min(65536, remain))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remain -= len(chunk)


def rebuild_topic_library_schedule(
    db_path: str | Path | None = None, path: Path | None = None
) -> str:
    """确认周选题后把 选题库.md 第 4 块「排期」重生成数据库镜像。

    定位：`## 4.` 标题行起、到下一个 `---` 或文末止，整块替换；第 0-3 块是夜班
    写稿的 prompt 输入源，不碰。临时文件 + replace 原子替换，防夜班 22:00 读到半截。
    """
    path = path or TOPIC_LIBRARY
    rows = [
        s for s in selection_db.list_selections(db_path)
        if s.get("status") == "scheduled" and s.get("scheduled_for")
    ]
    rows.sort(key=lambda s: (s["scheduled_for"], s["id"]))
    lines = [
        "## 4. 排期（确认周选题后由工作台自动回写）",
        "",
        "> 本块是选题台数据库的镜像：每次确认周选题后整块重生成，**手改会被覆盖**。",
        "> 要改排期去工作台选题台（「挪到下周」「回已选」），改完点一次确认周选题也会带上。",
        "",
        "| 日期 | 主题 | 预选 |",
        "|---|---|---|",
    ]
    for s in rows:
        d = s["scheduled_for"]
        try:
            wd = WEEKDAY_ZH[datetime.fromisoformat(d).weekday()]
        except ValueError:
            wd = ""
        note = "；".join(x for x in (s.get("project_full_name") or "", s.get("summary") or "") if x)
        lines.append("| %s（%s） | %s | %s |" % (d[5:], wd, s["title"], note or "—"))
    block = "\n".join(lines)
    text = _read_text(path)
    # 标题行用 [^\n] 收住（re.S 下 .*$ 会一路吞到文尾），块体懒匹配到下一个 --- 或文末
    m = re.search(r"^## 4\.[^\n]*\n.*?(?=^---$|\Z)", text, re.M | re.S)
    if m:
        new_text = text[:m.start()] + block + "\n\n" + text[m.end():].lstrip("\n")
    else:
        new_text = text.rstrip() + "\n\n---\n\n" + block + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(path)
    return block


def main() -> int:
    ap = argparse.ArgumentParser(description="播客本地选题台")
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--open", action="store_true", help="启动后打印地址")
    args = ap.parse_args()

    selection_db.init_db(selection_db.DB_PATH)
    reset_count = selection_db.reset_interrupted_tasks(selection_db.DB_PATH)
    claude_thread = threading.Thread(
        target=claude_select.run_worker,
        args=(STOP_EVENT, selection_db.DB_PATH),
        daemon=True,
        name="claude-selection-worker",
    )

    def feishu_worker() -> None:
        while not STOP_EVENT.is_set():
            if feishu_sync.is_configured():
                try:
                    result = feishu_sync.sync_once(selection_db.DB_PATH)
                    with SYNC_LOCK:
                        LAST_SYNC.update({
                            "ok": bool(result.get("ok")),
                            "at": selection_db.now(),
                            "result": result,
                            "error": "",
                        })
                except Exception as exc:  # noqa: BLE001
                    with SYNC_LOCK:
                        LAST_SYNC.update({
                            "ok": False,
                            "at": selection_db.now(),
                            "result": None,
                            "error": "%s: %s" % (type(exc).__name__, exc),
                        })
            STOP_EVENT.wait(300)

    sync_thread = threading.Thread(target=feishu_worker, daemon=True, name="feishu-sync-worker")
    weekly_thread = threading.Thread(
        target=weekly_select.run_worker,
        args=(STOP_EVENT, selection_db.DB_PATH),
        daemon=True,
        name="weekly-selection-worker",
    )
    claude_thread.start()
    sync_thread.start()
    weekly_thread.start()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = "http://127.0.0.1:%d/" % args.port
    print("[workbench] 绑 127.0.0.1:%d  %s" % (args.port, url))
    print("[workbench] 数据源: %s" % PROJECT_ROOT)
    if reset_count:
        print("[workbench] 恢复中断任务: %d" % reset_count)
    print("[workbench] Ctrl-C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[workbench] bye")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
