#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 output/episodes/ep*/page.md + output/*-episode.json + curated.json
合成网页资料库用的 episodes.json。

- 自动层只做定位（标题/日期/repo/音频/关联），不做判断的取舍
- 「一句话」「判断」一律来自人工精修层 data/curated.json（原话摘录）
- 脱敏：第三方人名 → 「原素材作者」；绝对路径、output/ 相对路径一律不留
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EP_DIR = ROOT / "output" / "episodes"
LIB = ROOT / "web" / "library"
CURATED = LIB / "data" / "curated.json"
OUT = LIB / "data" / "episodes.json"

SERIES = [
    (1, 1, "算力取舍", "#6b7a4a"),
    (2, 2, "开源协作", "#4a6b7a"),
    (3, 7, "Agent 这层壳", "#7a4a6b"),
    (8, 14, "攒得住的东西", "#8a6a3a"),
    (15, 19, "攒下的东西，怎么验", "#3a6b5a"),
    (20, 24, "能不能带走", "#5a5a7a"),
    (25, 30, "会不会自己烂掉", "#7a4a4a"),
    (31, 36, "AI 交了这么多", "#4a5a7a"),
    (37, 39, "你攒下的东西", "#6b4a3a"),
]


def clean(text: str) -> str:
    t = text.strip()
    t = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), t)
    t = t.replace("王振宇", "原素材作者")
    t = re.sub(r"/Users/[^\s，。；）)]*", "", t)
    t = re.sub(r"`?output/[^\s，。；）)`]*`?", "", t)
    t = t.replace("**", "").replace("`", "")
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip(" -—·，")


CJK = re.compile(r"[\u4e00-\u9fff]")


def script_path(md: str, slug: str, date: str, root: Path):
    """从页面里找这期的稿子文件，取不到就按日期/目录猜。"""
    m = re.search(r"稿子：\s*`?([^`\s，）)]+\.md)", md)
    cands = []
    if m:
        p = m.group(1)
        cands.append(root / p if p.startswith("output/") else root / "output" / p)
    if date:
        cands.append(root / "output" / f"{date}-script.md")
    d = root / "output" / "episodes" / slug
    if d.exists():
        cands += sorted(d.glob("*script*.md"))
    for c in cands:
        if c.exists() and c.stat().st_size > 2000:
            return c
    return None


def split_title(raw: str):
    t = re.sub(r"^第\s*\d+\s*期\s*·\s*", "", raw)
    t = re.sub(r"^ep\d+\s*·\s*", "", t)
    head, sep, tail = t.partition("——")
    return clean(head), clean(tail) if sep else ""


def main():
    curated = json.loads(CURATED.read_text(encoding="utf-8"))
    eps = []
    for f in sorted(EP_DIR.glob("ep*/page.md"),
                    key=lambda p: int(re.match(r"ep(\d+)", p.parent.name).group(1))):
        slug = f.parent.name
        no = int(re.match(r"ep(\d+)", slug).group(1))
        md = f.read_text(encoding="utf-8")
        first = md.splitlines()[0]
        title, subtitle = split_title(first[2:].strip() if first.startswith("# ") else first)

        repos = [m.group(1).split("（")[0].split("(")[0].strip() for m in re.finditer(r"^-\s*repo:\s*(\S+)", md, re.M)]
        dm = re.search(r"上线：\s*(\d{4}-\d{2}-\d{2})", md)
        date = dm.group(1) if dm else ""

        # 音频：只认「豆包 seed-audio」产物（<主题>-播客完整版-Nmin.m4a）。
        # MiMo 克隆音色的期次含第三方音色，不放入公开站。
        audio = None
        m = re.search(r"音频：[^\n]*?output/audio/([^\s`）)]+\.m4a)", md)
        if m:
            fn = m.group(1)
            mm = re.match(r"(.+)-播客完整版-(\d+)min\.m4a$", fn)
            if mm:
                audio = {"file": fn, "minutes": int(mm.group(2))}

        question = ""
        jf = ROOT / "output" / f"{date}-episode.json"
        if date and jf.exists():
            try:
                question = clean(json.loads(jf.read_text(encoding="utf-8")).get("question") or "")
            except Exception:
                question = ""

        related = []
        for lm in re.finditer(r"\[\[(ep\d+[\w-]*)\]\]", md):
            s = lm.group(1)
            if s != slug and s not in related:
                related.append(s)

        series, color = next(((name, c) for lo, hi, name, c in SERIES if lo <= no <= hi), ("", ""))
        sp = script_path(md, slug, date, ROOT)
        chars = 0
        if sp:
            chars = len(CJK.findall(sp.read_text(encoding="utf-8", errors="ignore")))
        cur = curated.get(str(no), {})
        eps.append({
            "no": no,
            "slug": slug,
            "title": title,
            "subtitle": subtitle,
            "series": series,
            "color": color,
            "chars": chars,
            "month": date[:7],
            "date": date,
            "question": question,
            "one_liner": clean(cur.get("one_liner", "")),
            "judgments": [clean(j) for j in cur.get("judgments", [])],
            "repos": repos,
            "audio": audio,
            "related": related,
        })

    dates = sorted(e["date"] for e in eps if e["date"])
    data = {
        "count": len(eps),
        "judgment_count": sum(len(e["judgments"]) for e in eps),
        "judged_count": sum(1 for e in eps if e["judgments"]),
        "repo_count": len({r for e in eps for r in e["repos"]}),
        "audio_count": sum(1 for e in eps if e["audio"]),
        "audio_minutes": sum(e["audio"]["minutes"] for e in eps if e["audio"]),
        "first_date": dates[0] if dates else "",
        "last_date": dates[-1] if dates else "",
        "series": [name for _, _, name, _ in SERIES],
        "series_meta": [{"name": n, "color": c} for _, _, n, c in SERIES],
        "chars_total": sum(e["chars"] for e in eps),
        "chars_max": max((e["chars"] for e in eps), default=0),
        "episodes": eps,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (LIB / "data.js").write_text(
        "/* 自动生成，别手改；来源 scripts/build_library_data.py */\nwindow.LIB = "
        + json.dumps(data, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT}")
    print(f"  {data['count']} 期 / {data['judgment_count']} 条判断（{data['judged_count']} 期有判断）"
          f" / {data['repo_count']} 个仓库 / {data['audio_count']} 期有豆包音频"
          f" / {data['first_date']} → {data['last_date']}"
          f" / 讲稿合计 {data['chars_total']:,} 汉字（最多一期 {data['chars_max']:,}）")
    bad = [e["slug"] for e in eps if not e["title"]]
    if bad:
        print("标题缺失：", bad)


if __name__ == "__main__":
    sys.exit(main())
