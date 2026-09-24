#!/usr/bin/env python3
"""Episode picker — selects 1 GitHub project + 3-5 news items for one podcast episode.

Rules (from 任务书):
  - project: stars>=3000, category in {图像/视频生成, 语音, Agent/LLM},
    pushed within 90 days, not already in output/episodes.log
  - news: aihot v1 selected items (24h window), filtered for relevance
    to the three focus lines or major industry events
Output: output/<date>-brief.md ; appends project name to output/episodes.log

Network note: the shell env carries a dead proxy (127.0.0.1:7890), so all
HTTP here goes through a no-proxy opener, and git is invoked with proxy
overrides. See BLOCKED.md.
"""

import json
import re
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "info_source.db"
CACHE_DIR = ROOT / "cache"
OUT_DIR = ROOT / "output"
LOG_PATH = OUT_DIR / "episodes.log"

AIHOT_URL = "https://aihot.news/api/v1/items?mode=selected&window=24h&limit=50"
GH_API = "https://api.github.com/repos/{full_name}"

# Last episode (podcast-01) covered whisper.cpp, category 语音.
LAST_EPISODE_CATEGORY = "语音"
LAST_EPISODE_PROJECT = "ggml-org/whisper.cpp"

# Skip list-ish repos: no core code to read for a 35-min deep dive.
LIST_PAT = re.compile(
    r"awesome|curated list|prompts\.chat|course|roadmap|checklist|guide|"
    r"papers? collection|interview| encyclopedia",
    re.IGNORECASE,
)

# Keywords mapping news items to the three focus lines.
LINE_KEYWORDS = {
    "图像/视频生成": [
        "图像", "生图", "视频生成", "文生视频", "图生视频", "diffusion", "扩散",
        "stable diffusion", "midjourney", "sora", "veo", "seedream", "写真",
        "image", "video generation", "text-to-video", "flux", "comfyui",
    ],
    "语音": [
        "语音", "tts", "asr", "语音识别", "语音合成", "whisper", "播客",
        "audio", "speech", "voice", "配音", "克隆", "声音",
    ],
    "Agent/LLM": [
        "agent", "智能体", "llm", "大模型", "gpt", "claude", "gemini", "开源模型",
        "mcp", "工作流", "automation", "copilot", "编码", "编程", "推理模型",
        "reasoning", "context", "记忆", "fine-tune", "微调", "蒸馏",
    ],
}
# Major industry events worth covering regardless of line.
MAJOR_PAT = re.compile(
    r"openai|anthropic|google|meta|microsoft|nvidia|apple|深度求索|deepseek|"
    r"上市|融资|收购|发布|开源|发布万亿|参数|旗舰|发布会|gpt-\d|监管|禁令",
    re.IGNORECASE,
)

CODE_EXT = {".py", ".c", ".cpp", ".h", ".go", ".rs", ".ts", ".tsx", ".js",
            ".java", ".swift", ".kt", ".sh", ".toml", ".yaml", ".yml", ".json"}


def http_json(url, headers=None):
    """Fetch JSON with proxy disabled (env proxy is dead)."""
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "episode-picker"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_candidates():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT full_name, category, url, description, stars, language "
        "FROM projects WHERE is_overseas=1 AND stars>=3000 ORDER BY stars DESC"
    ).fetchall()
    conn.close()
    return [dict(zip(("full_name", "category", "url", "description",
                      "stars", "language"), r)) for r in rows]


def load_done_projects():
    if not LOG_PATH.exists():
        # Seed with the project used in podcast-01.
        return {LAST_EPISODE_PROJECT}
    return {line.strip() for line in LOG_PATH.read_text().splitlines() if line.strip()}


def pushed_within_days(full_name, days=90):
    try:
        data = http_json(GH_API.format(full_name=full_name))
    except Exception as e:
        print(f"[!] GitHub API 查询失败 {full_name}: {e}", file=sys.stderr)
        return False, None
    pushed = datetime.strptime(data["pushed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - pushed
    return age <= timedelta(days=days), data


def latest_release_within_days(full_name, days=30):
    """近 N 天有没有发版。拿不到 release 就返回 None（不是失败）。

    返回 (是否在窗口内, 发布日期字符串, tag 名) 或 None。
    """
    url = f"https://api.github.com/repos/{full_name}/releases/latest"
    try:
        data = http_json(url)
    except Exception:
        return None
    raw = data.get("published_at") or ""
    if not raw:
        return None
    try:
        when = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    age = datetime.now(timezone.utc) - when
    return age <= timedelta(days=days), raw, data.get("tag_name")


def latest_commit_sha(full_name):
    """默认分支最新 commit 短哈希；拿不到返回 None。"""
    try:
        data = http_json(f"https://api.github.com/repos/{full_name}/commits?per_page=1")
        return (data[0]["sha"][:7] if data else None)
    except Exception:
        return None


def pick_project(candidates, done):
    # Prefer rotating off last episode's category when alternatives exist.
    pools = ([c for c in candidates if c["category"] != LAST_EPISODE_CATEGORY]
             or candidates)
    checked = 0
    # 时效闸（软）：优先挑「近 30 天有 release」的，但**不硬砍**——
    # 免得误杀「很活跃、但就是不发 release」的项目（如 n8n 这类）。
    first_active = None
    for c in pools:
        if c["full_name"] in done:
            continue
        if LIST_PAT.search(c["full_name"]) or LIST_PAT.search(c["description"] or ""):
            continue
        checked += 1
        if checked > 15:  # API budget guard
            break
        ok, meta = pushed_within_days(c["full_name"])
        rel = latest_release_within_days(c["full_name"])
        tag = rel[2] if rel else "-"
        print(f"[.] {c['full_name']} ⭐{c['stars']} push90d={'Y' if ok else 'N'} "
              f"release30d={'Y' if (rel and rel[0]) else 'N'} tag={tag}")
        if not ok:
            continue
        c["pushed_at"] = meta["pushed_at"]
        c["default_branch"] = meta.get("default_branch", "main")
        c["size_kb"] = meta.get("size", 0)
        c["release_tag"] = tag
        c["release_date"] = (rel[1][:10] if rel else None)
        c["release_recent"] = bool(rel and rel[0])
        # 第一个「近 30 天有 release」的优先返回；否则记下第一个活跃的当备选
        if c["release_recent"]:
            return c
        if first_active is None:
            first_active = c
    return first_active


def clone_project(full_name):
    CACHE_DIR.mkdir(exist_ok=True)
    dest = CACHE_DIR / full_name.split("/")[-1]
    if dest.exists():
        print(f"[.] cache 已存在: {dest}")
        return dest
    url = f"https://github.com/{full_name}.git"
    # -c http.proxy= : neutralize the dead global gitconfig proxy (see BLOCKED.md)
    r = subprocess.run(
        ["git", "-c", "http.proxy=", "-c", "https.proxy=",
         "clone", "--depth", "1", url, str(dest)],
        capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return None
    return dest


def repo_tree(repo_dir, max_depth=2, max_entries=120):
    lines = []
    count = 0
    for p in sorted(repo_dir.rglob("*")):
        if any(part.startswith(".") and part != "." for part in p.relative_to(repo_dir).parts):
            continue
        rel = p.relative_to(repo_dir)
        if len(rel.parts) > max_depth:
            continue
        marker = "/" if p.is_dir() else ""
        lines.append(f"{'  ' * (len(rel.parts) - 1)}- {rel.parts[-1]}{marker}")
        count += 1
        if count >= max_entries:
            lines.append("  …(截断)")
            break
    return "\n".join(lines)


def core_files(repo_dir, max_files=15):
    """Heuristic core-file list: top-level code files + biggest code files."""
    files = [p for p in repo_dir.rglob("*")
             if p.is_file() and p.suffix.lower() in CODE_EXT
             and not any(part.startswith(".") for part in p.relative_to(repo_dir).parts)]
    files.sort(key=lambda p: (len(p.relative_to(repo_dir).parts), -p.stat().st_size))
    out, seen_dirs = [], set()
    for p in files:
        rel = str(p.relative_to(repo_dir))
        top = rel.split("/")[0] if "/" in rel else ""
        if top in seen_dirs and len(out) >= max_files // 2:
            continue
        out.append((rel, p.stat().st_size))
        if top:
            seen_dirs.add(top)
        if len(out) >= max_files:
            break
    return out


def pick_news():
    data = http_json(AIHOT_URL)
    items = data.get("items", [])
    print(f"[.] aihot 精选 {len(items)} 条")
    hits = []
    for it in items:
        text = " ".join([it.get("title") or "", it.get("summary") or ""])
        line = next((ln for ln, kws in LINE_KEYWORDS.items()
                     if any(kw in text.lower() or kw in text for kw in kws)), None)
        major = bool(MAJOR_PAT.search(text))
        if line or major:
            hits.append({"item": it, "line": line or "重大事件", "major": major,
                         "score": it.get("score", 0)})
    hits.sort(key=lambda h: (not h["major"], -h["score"]))
    return hits[:5], len(items)


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    done = load_done_projects()
    candidates = load_candidates()
    print(f"[.] 候选 {len(candidates)} 个，已用过 {len(done)} 个")

    proj = pick_project(candidates, done)
    if not proj:
        print("[!] 没有合格项目", file=sys.stderr)
        sys.exit(1)
    print(f"[✓] 选定项目: {proj['full_name']}")

    repo_dir = clone_project(proj["full_name"])
    if repo_dir is None:
        print("[!] clone 失败", file=sys.stderr)
        sys.exit(1)

    news, total = pick_news()

    # ---- write brief ----
    brief = [f"# 播客选料简报 · {today}", ""]
    brief.append("## 候选池说明（选料范围）")
    brief.append("")
    brief.append(f"- 海外 GitHub：`output/{today}.md`（fetch.py 产出）")
    brief.append(f"- 海外论文/发布：`output/{today}-sources.md`（若存在）")
    brief.append(f"- 国内大厂（DeepSeek/千问/字节/智谱）：`output/{today}-cn-sources.md`（若存在，白名单制）")
    brief.append("- 选题库第 3 块点名要听国内某家时，优先国内池。")
    brief.append("")
    brief.append("## 本期项目")
    brief.append("")
    brief.append(f"- **{proj['full_name']}** ⭐{proj['stars']} ｜ 主线：{proj['category']} ｜ 语言：{proj['language'] or '未知'}")
    brief.append(f"- 链接：{proj['url']}")
    brief.append(f"- 最近 push：{proj['pushed_at']}")
    brief.append(f"- 信息截止：{today}")
    if proj.get("release_recent") and proj.get("release_tag") not in (None, "-"):
        brief.append(f"- 当前版本：{proj['release_tag']}（release {proj.get('release_date')}，近 30 天有发版）")
    else:
        sha = latest_commit_sha(proj["full_name"]) or "取不到"
        tag = proj.get("release_tag")
        brief.append(f"- 当前版本：无近 30 天 release（最新 tag={tag or '-'}），按默认分支 commit {sha}")
    brief.append(f"- 简介：{proj['description'] or '（无）'}")
    brief.append("")
    brief.append("### 目录结构（深度 2）")
    brief.append("")
    brief.append(repo_tree(repo_dir))
    brief.append("")
    brief.append("### 核心文件清单（启发式：顶层 + 大文件优先）")
    brief.append("")
    for rel, size in core_files(repo_dir):
        brief.append(f"- `{rel}` ({size / 1024:.1f} KB)")
    brief.append("")
    brief.append(f"## 新闻段（aihot 当日精选 {total} 条中筛 {len(news)} 条）")
    brief.append("")
    for i, h in enumerate(news, 1):
        it = h["item"]
        brief.append(f"### {i}. {it.get('title') or it.get('originalTitle')}")
        brief.append("")
        brief.append(f"- 主线标签：{h['line']}" + ("（重大事件）" if h["major"] else ""))
        brief.append(f"- 原文：{(it.get('links') or {}).get('original')}")
        brief.append(f"- 来源：{(it.get('source') or {}).get('name')} ｜ {it.get('publishedAt')}")
        brief.append(f"- 摘要：{it.get('summary') or '（无）'}")
        brief.append("")

    OUT_DIR.mkdir(exist_ok=True)
    brief_path = OUT_DIR / f"{today}-brief.md"
    brief_path.write_text("\n".join(brief), encoding="utf-8")
    print(f"[✓] 简报已写入 {brief_path}")

    if not LOG_PATH.exists():
        LOG_PATH.write_text(LAST_EPISODE_PROJECT + "\n", encoding="utf-8")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{proj['full_name']}\n")
    print(f"[✓] {proj['full_name']} 已追加进 episodes.log")


if __name__ == "__main__":
    main()
