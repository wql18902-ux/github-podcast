#!/usr/bin/env python3
"""国内大厂源抓取 —— 白名单制（2026-09-11 用户拍板加入）。

边界：只收大公司 —— DeepSeek / 千问（Qwen）/ 字节 / 智谱。国内小厂、个人项目一律不收。
     白名单里只写这几家，不写的不进。

红线怎么绕：fetch.py 的 KNOWN_CN_ORGS 是「海外池的排除名单，一个字不许改」。
     所以国内源不能靠改黑名单实现，只能走本脚本（独立白名单），写自己的
     output/<日期>-cn-sources.md，与海外池并行、互不干涉。

实测坑（2026-09-11 复测，全部写死在这里别踩）：
  1. arXiv 必须 https —— http://export.arxiv.org/... 返回空（0 entry）。
  2. 论文只能用 au:"集体作者名"。all:DeepSeek 是模糊匹配，命中别家论文。
  3. 智谱 arXiv 按机构名搜不到（au:"Zhipu AI" = 0 条），故意缺席 CN_ARXIV_AUTHORS，
     只走 GitHub org + 官网更新页。

窗口：论文 60 天（用户拍板「两个月以内」）；仓库 30 天。海外侧仍 14 天，两边独立。
      60 天下国内论文段可能长期为空 —— 正常，不是失败。日常的「新」靠 org 日更 + 官网。
"""
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "output"

# ---------- 白名单（唯一需要人工维护的地方：加公司就加一行） ----------
CN_ORGS = [
    ("DeepSeek", "deepseek-ai"),
    ("Qwen", "QwenLM"),
    ("ByteDance", "bytedance"),
    ("ByteDance", "ByteDance-Seed"),
    ("Zhipu", "zai-org"),
    ("Zhipu", "THUDM"),
]
# arXiv 集体作者名：实测有命中的才写进来；智谱实测无命中，故意缺席（走官网更新页）
CN_ARXIV_AUTHORS = [
    ("DeepSeek", 'au:"DeepSeek-AI"'),
    ("Qwen", 'au:"Qwen Team"'),
    ("ByteDance", 'au:"ByteDance Seed"'),
]
CN_BLOGS = [
    # (显示名, 地址, 类型)   type: rss | html | skip
    # 实测（2026-09-11）：Qwen 老 RSS 停在 2025-09（新博客 qwen.ai 是 JS 站，静态抓不到）；
    # 字节/智谱官网也是 JS 渲染 → 这三家官网源标记 skip，日常「新」靠 GitHub org 日更兜底。
    # 只有 DeepSeek 更新页静态可抓（h2=日期 + h3=版本名），保留。
    ("DeepSeek 更新", "https://api-docs.deepseek.com/updates/", "html"),
    ("Qwen 官方博客", "https://qwenlm.github.io/blog/index.xml", "skip"),
    ("字节 Seed", "https://seed.bytedance.com/zh/research", "skip"),
    ("智谱更新日志", "https://docs.bigmodel.cn/cn/guide/start/introduction", "skip"),
]
CN_BLOG_WINDOW_DAYS = 90    # 发布条目窗口：只要近 90 天的（老的更新日志不进日报）
CN_PAPER_WINDOW_DAYS = 60   # 国内论文窗口 60 天（2026-09-11 用户拍板「两个月以内」；海外仍 14 天）
CN_REPO_WINDOW_DAYS = 30    # 活跃仓库窗口（pushed_at 或 created_at 在 30 天内）

UA = {"User-Agent": "cn-sources-fetcher"}


def http_get(url, timeout=30):
    """带死代理绕过的 GET（环境代理常死，见项目 AGENTS.md 环境陷阱 1）。"""
    req = urllib.request.Request(url, headers=UA)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        return resp.read()


def http_json(url, timeout=30):
    return json.loads(http_get(url, timeout).decode("utf-8"))


def days_ago(iso_ts):
    """ISO8601（Z 结尾）→ 距今天数；解析不了返回 None。"""
    try:
        when = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return (datetime.now(timezone.utc) - when).days


def _days_from_date(date_str):
    """'2026-09-10' → 距今天数；解析不了返回 None。"""
    try:
        when = datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return (datetime.now(timezone.utc) - when).days


# ---------- 三个抓取函数 ----------
def fetch_org_repos(org, company):
    """活跃仓库：pushed_at 或 created_at 在 30 天内的（新仓库也算「新」）。"""
    url = f"https://api.github.com/orgs/{org}/repos?sort=pushed&per_page=10"
    data = http_json(url)
    out = []
    for r in data:
        if r.get("fork"):
            continue
        age_p = days_ago(r.get("pushed_at") or "")
        age_c = days_ago(r.get("created_at") or "")
        fresh = ((age_p is not None and age_p <= CN_REPO_WINDOW_DAYS)
                 or (age_c is not None and age_c <= CN_REPO_WINDOW_DAYS))
        if not fresh:
            continue
        out.append({
            "company": company, "full_name": r["full_name"],
            "stars": r.get("stargazers_count", 0),
            "desc": (r.get("description") or "").strip(),
            "pushed": (r.get("pushed_at") or "")[:10],
            "url": r.get("html_url", ""),
        })
    return out


def fetch_arxiv(author_query, company):
    """arXiv 集体作者查询（必须 https）。"""
    base = "https://export.arxiv.org/api/query"
    url = (f"{base}?search_query={urllib.parse.quote(author_query)}"
           f"&sortBy=submittedDate&sortOrder=descending&max_results=20")
    raw = http_get(url)
    root = ET.fromstring(raw)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in root.findall("a:entry", ns):
        title = " ".join((e.findtext("a:title", "", ns) or "").split())
        published = (e.findtext("a:published", "", ns) or "")[:10]
        link = e.findtext("a:id", "", ns) or ""
        age = days_ago(published + "T00:00:00Z")
        if age is None or age > CN_PAPER_WINDOW_DAYS:
            continue
        out.append({"company": company, "title": title, "date": published, "url": link})
    return out


TAG_RE = re.compile(r"<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", re.S)
H_RE = re.compile(r"<h([234])[^>]*>(.*?)</h\1>", re.S)
STRIP_RE = re.compile(r"<[^>]+>")
# 明显是导航/工具链的标题，别当内容条目
NAV_NOISE_RE = re.compile(
    r"^(skip to|english|中文|quick start|your first|models &|token &|rate limit|error codes|"
    r"api guide|api reference|change log|news$|other resources|platform|deepseek platform|"
    r"^查看|^加入我们|^博客$|^精选论文$|^infrastructures$|^this documentation|^documentation)",
    re.IGNORECASE,
)


def _clean(html_frag):
    return " ".join(STRIP_RE.sub("", html_frag).split()).replace("\u200b", "")


def fetch_blog(name, url, kind):
    """官方发布：rss 走 xml 解析；html 按各家结构抓真条目。
    保守原则：抓不到就抛错（调用方写 [!]），绝不把导航噪音当条目。
    kind == "skip"：实测 JS 渲染抓不到 → 直接返回空（不算错误，静默跳过）。"""
    if kind == "skip":
        return []
    raw = http_get(url)
    items = []
    text = raw.decode("utf-8", errors="replace")

    if kind == "rss":
        root = ET.fromstring(raw)
        for e in root.findall(".//item")[:15]:
            title = (e.findtext("title") or "").strip()
            link = (e.findtext("link") or "").strip()
            date = (e.findtext("pubDate") or "").strip()
            if title:
                items.append({"name": name, "title": title, "url": link, "date": date})
        if not items:
            raise RuntimeError("RSS 解析出 0 条")
        return items

    # html：优先看有没有 h2/h3 条目结构（如 DeepSeek 更新页：h2=日期、h3=版本名）
    heads = H_RE.findall(text)
    if heads:
        pending_date = ""
        for level, frag in heads:
            title = _clean(frag)
            if not title or NAV_NOISE_RE.match(title):
                continue
            if title.startswith("Date:"):
                pending_date = title.replace("Date:", "").strip()
                continue
            # 时间过滤：有日期且超过窗口的丢弃（更新日志里的老条目别进日报）
            if pending_date:
                age = _days_from_date(pending_date)
                if age is not None and age > CN_BLOG_WINDOW_DAYS:
                    continue
            items.append({"name": name, "title": title, "url": url,
                          "date": pending_date})
            if len(items) >= 15:
                break
        if items:
            return items

    # 退回抓链接：但过滤导航噪音
    for href, inner in TAG_RE.findall(text):
        title = _clean(inner)
        if not title or len(title) < 6 or NAV_NOISE_RE.match(title):
            continue
        if href.startswith("/"):
            from urllib.parse import urlparse
            p = urlparse(url)
            href = f"{p.scheme}://{p.netloc}{href}"
        items.append({"name": name, "title": title, "url": href, "date": ""})
        if len(items) >= 15:
            break

    if not items:
        raise RuntimeError("HTML 页面没抓到内容条目（可能是 JS 渲染，静态抓不到）")
    return items


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    errors = []
    repos, papers, blogs = [], [], []

    # 1) GitHub org 活跃仓库
    for company, org in CN_ORGS:
        try:
            repos.extend(fetch_org_repos(org, company))
        except Exception as e:
            errors.append(f"{org} 仓库查询失败: {e}")

    # 2) arXiv 论文
    for company, query in CN_ARXIV_AUTHORS:
        try:
            papers.extend(fetch_arxiv(query, company))
        except Exception as e:
            errors.append(f"{company} arXiv 查询失败: {e}")

    # 3) 官方发布
    for name, url, kind in CN_BLOGS:
        try:
            blogs.extend(fetch_blog(name, url, kind))
        except Exception as e:
            errors.append(f"{name} 查询失败: {e}")

    # 去重（按 url）+ 排序
    repos = sorted({r["url"]: r for r in repos}.values(), key=lambda x: x["pushed"], reverse=True)
    papers = sorted({p["url"]: p for p in papers}.values(), key=lambda x: x["date"], reverse=True)
    seen_b = set()
    blogs_dedup = []
    for b in blogs:
        key = (b["name"], b["title"])
        if key in seen_b:
            continue
        seen_b.add(key)
        blogs_dedup.append(b)
    blogs = blogs_dedup

    lines = [f"# 国内大厂源 · {today}（白名单：DeepSeek / 千问 / 字节 / 智谱）", ""]

    lines.append(f"## 活跃仓库（近 {CN_REPO_WINDOW_DAYS} 天有 push 或新建）")
    lines.append("")
    if repos:
        for r in repos[:30]:
            desc = f" — {r['desc']}" if r["desc"] else ""
            lines.append(f"- [{r['company']}] **{r['full_name']}** ⭐{r['stars']}{desc} "
                         f"｜ push {r['pushed']} ｜ {r['url']}")
    else:
        lines.append("（无）")
    lines.append("")

    lines.append("## 官方发布")
    lines.append("")
    if blogs:
        for b in blogs:
            d = f" — {b['date']}" if b["date"] else ""
            lines.append(f"- [{b['name']}] {b['title']}{d} ｜ {b['url']}")
    else:
        lines.append("（无）")
    lines.append("")

    lines.append(f"## 论文（arXiv 集体作者，近 {CN_PAPER_WINDOW_DAYS} 天）")
    lines.append("")
    if papers:
        for p in papers:
            lines.append(f"- [{p['company']}] **{p['title']}** — {p['date']} ｜ {p['url']}")
    else:
        lines.append(f"（近 {CN_PAPER_WINDOW_DAYS} 天无新论文——国内四家发得少，空着是正常结果，不是失败）")
    lines.append("")

    if errors:
        for e in errors:
            lines.append(f"[!] {e}")
        lines.append("")

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"{today}-cn-sources.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[✓] 已写入 {out_path}")
    print(f"    仓库 {len(repos)} 条 ｜ 发布 {len(blogs)} 条 ｜ 论文 {len(papers)} 条")
    if errors:
        for e in errors:
            print(f"    [!] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
