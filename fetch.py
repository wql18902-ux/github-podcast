#!/usr/bin/env python3
"""GitHub AI open-source project fetcher — builds a daily info source.

Pulls high-star AI repos from the GitHub Search API, drops Chinese /
republished repos, tags each repo with one of the listener's focus areas
(see config/audience.md), stores everything in SQLite, and writes a daily
markdown digest.

Pure stdlib (urllib + sqlite3 + json). No third-party deps, no API key.
Run:  python3 fetch.py
"""

import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API = "https://api.github.com/search/repositories"
HEADERS = {
    "User-Agent": "info-source-fetcher",
    "Accept": "application/vnd.github+json",
}

# (category, query, min_stars). 这三类对应听众画像（config/audience.md）里的三条主线：
#   图像/视频生成 -> 主线一
#   语音          -> 主线二
#   Agent/LLM     -> 主线三
# 换成你自己的方向就改这一处：分类名会一路带到选稿和写稿链路。
QUERIES = [
    ("图像/视频生成", "topic:image-generation stars:>2000", 2000),
    ("图像/视频生成", "topic:text-to-video stars:>1500", 1500),
    ("语音",          "topic:text-to-speech stars:>1500", 1500),
    ("语音",          "topic:speech-recognition stars:>1000", 1000),
    ("Agent/LLM",     "topic:ai-agents stars:>3000", 3000),
    ("Agent/LLM",     "topic:llm stars:>5000", 5000),
    ("Agent/LLM",     "topic:mcp stars:>1000", 1000),
]

PER_PAGE = 20

# A repo whose description contains CJK is almost certainly Chinese or a
# Chinese translation of a foreign project.
CJK = re.compile(r"[一-鿿]")

# Known Chinese orgs/authors whose repos use English descriptions. v1
# blocklist — extend by hand; README-language check is the proper v2 fix.
KNOWN_CN_ORGS = {
    "qwenlm", "qwenaudio", "modelscope", "paddlepaddle", "paddlenlp",
    "tencent-hunyuan", "tencent", "bytedance", "deepseek-ai",
    "internlm", "openbmb", "thudm", "pku-yuangroup", "openmmlab",
    "zai-org", "k2-fsa", "funaudio", "index-tts",
    "rvc-boss", "2noise", "babysor", "jianchang512", "op7418",
    "lingyichen-ai", "yangling0818", "chenhsing", "ailab-cvc",
    "snailclimb", "harry0703", "nl8590687", "panniantong",
    "lobehub", "infiniflow", "langgenius",
}

DB_PATH = "info_source.db"


# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------

def search_repos(query, per_page=PER_PAGE, retries=2):
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": str(per_page),
    }
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 403 and attempt < retries:
                print(f"[!] 触发 rate limit，等 60 秒重试 ({attempt + 1}/{retries})...", file=sys.stderr)
                time.sleep(60)
                continue
            raise


def is_overseas(repo):
    """v1 heuristic: no CJK in description AND owner not a known CN org.

    v2 upgrade: inspect the README language (extra API call per repo),
    since the blocklist can't be exhaustive.
    """
    desc = repo.get("description") or ""
    if CJK.search(desc):
        return False
    owner = (repo.get("owner") or {}).get("login", "").lower()
    return owner not in KNOWN_CN_ORGS


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            full_name   TEXT PRIMARY KEY,
            category    TEXT,
            url         TEXT,
            description TEXT,
            stars       INTEGER,
            language    TEXT,
            topics      TEXT,          -- JSON array
            is_overseas INTEGER,       -- 1 = overseas, 0 = dropped (Chinese)
            first_seen  TEXT,
            last_seen   TEXT
        )
    """)


def upsert(conn, repo, category, overseas, now):
    topics = json.dumps(repo.get("topics", []), ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO projects
            (full_name, category, url, description, stars, language, topics,
             is_overseas, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(full_name) DO UPDATE SET
            stars = excluded.stars,
            category = excluded.category,
            is_overseas = excluded.is_overseas,
            last_seen = excluded.last_seen
        """,
        (
            repo["full_name"],
            category,
            repo["html_url"],
            repo.get("description") or "",
            repo["stargazers_count"],
            repo.get("language") or "",
            topics,
            overseas,
            now,
            now,
        ),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    seen = {}  # full_name -> (category, repo, overseas)
    for category, query, _min in QUERIES:
        try:
            data = search_repos(query)
        except Exception as e:
            print(f"[!] 查询失败 {query!r}: {e}", file=sys.stderr)
            continue

        items = data.get("items", [])
        print(f"[.] {category:10s} {query:40s} -> {len(items)} 个")

        for repo in items:
            name = repo["full_name"]
            if name in seen:
                continue
            overseas = is_overseas(repo)
            seen[name] = (category, repo, overseas)

        time.sleep(7)  # stay under the unauthenticated search API's 10 req/min

    # Persist everything, split by overseas flag for the digest.
    for name, (category, repo, overseas) in seen.items():
        upsert(conn, repo, category, 1 if overseas else 0, now)

    overseas = [(n, c, r) for n, (c, r, o) in seen.items() if o]
    dropped = [(n, c, r) for n, (c, r, o) in seen.items() if not o]

    conn.commit()
    conn.close()

    write_digest(overseas, dropped, now)
    print(f"\n[✓] 入库 {len(seen)} 个，海外 {len(overseas)} 个，中文/搬运排除 {len(dropped)} 个")


def write_digest(overseas, dropped, now):
    date = now[:10]
    path = f"output/{date}.md"
    by_cat = {}
    for name, cat, repo in sorted(overseas, key=lambda x: -x[2]["stargazers_count"]):
        by_cat.setdefault(cat, []).append(repo)

    lines = [f"# AI 开源项目信息源 · {date}", ""]
    lines.append(f"共 {len(overseas)} 个海外高赞项目（已排除 {len(dropped)} 个中文/搬运）。\n")

    for cat in ["图像/视频生成", "语音", "Agent/LLM"]:
        repos = by_cat.get(cat, [])
        if not repos:
            continue
        lines.append(f"## {cat}")
        lines.append("")
        for r in repos:
            star = r["stargazers_count"]
            desc = (r.get("description") or "").strip()
            lines.append(f"- **{r['full_name']}** ⭐{star} — {desc}")
            lines.append(f"  {r['html_url']}")
        lines.append("")

    if dropped:
        lines.append("## 已排除（中文/搬运，仅供排查）")
        lines.append("")
        for name, cat, repo in sorted(dropped, key=lambda x: -x[2]["stargazers_count"]):
            lines.append(f"- {name} ⭐{repo['stargazers_count']} — {(repo.get('description') or '').strip()[:50]}")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[✓] 清单已写入 {path}")


if __name__ == "__main__":
    main()
