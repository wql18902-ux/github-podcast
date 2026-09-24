#!/usr/bin/env python3
"""口播稿切段：剥 markdown → 合并自然段 → 按语速反推每段 duration。

用法:
    python3 scripts/split_segments.py <文稿.md> [PACE] [输出目录] [--unit char|han]

产出:
    <输出目录>/segNN.txt      每段正文
    <输出目录>/manifest.json  {"seg01": 秒, ...}
    控制台一份切稿报告（段数/总时长/真实语速/异常提示）

## PACE 口径（关键，别混用）

中文稿标点约占 30%，「字数」到底指什么直接决定成品时长，两档差 40%：

    --unit char（默认，历史行为）  PACE = 字符/秒（含标点）
        PACE 3.58 → 字符 3.58/秒，但汉字只有 ~2.5/秒 = 150 汉字/分钟
        这正是「标称 45 分钟、实际 60 分钟」的来源：标称按汉字算，脚本按字符算。

    --unit han                    PACE = 汉字/秒
        要 220 汉字/分钟就传 3.67；要 150 汉字/分钟（历史从容档）传 2.50

不论哪一档，脚本都会打印**两种口径的真实语速**，免得再出现「标称对不上实际」。

## 两个修复点

1. TARGET 由 PACE 推导（= int(120 * PACE)），不再硬编码 440。
   旧值 440 在 PACE 3.58 下算出 122.9s，必然撞 120s 上限被 clip，
   实际语速被抬到 3.67（+2%），且段落越长偏差越大。
2. 短段（< 30s 量）合并到相邻段，而不是 clip 到 30s。
   旧行为把 50 字段强拉到 30s → 语速 1.67/秒，比目标慢 53%，听感突兀。
"""
import sys
import os
import re
import glob
import json

HAN = re.compile(r"[\u4e00-\u9fff]")
MAX_SEC = 120  # 工具硬上限
MIN_SEC = 30   # 低于此量就合并，不硬拉


def measure(s: str, unit: str) -> int:
    """按口径量一段文字的「字数」。"""
    return len(HAN.findall(s)) if unit == "han" else len(s)


def split_long(p: str, target: int, unit: str):
    """单个自然段超过 target 时按句号→逗号逐级拆开，绝不在半句切断。

    n8n 那期就栽在这：稿子里有几个 800+ 字的超长段，只按自然段切会算出
    230-290s，直接撞 120s 上限被 clip，语速失真近一倍。文档规则 6 有这条，
    但旧的内联脚本没实现。
    """
    if measure(p, unit) <= target:
        return [p]

    def pack(pieces):
        out, buf = [], ""
        for x in pieces:
            x = x.strip()
            if not x:
                continue
            if not buf:
                buf = x
            elif measure(buf, unit) + measure(x, unit) <= target:
                buf += x
            else:
                out.append(buf)
                buf = x
        if buf:
            out.append(buf)
        return out

    # 先按句末标点拆
    segs = pack(re.split(r"(?<=[。！？!?])", p))
    # 仍有超长的（单句本身就长），按逗号再拆
    final = []
    for s in segs:
        if measure(s, unit) > target:
            final.extend(pack(re.split(r"(?<=[，,；;、])", s)))
        else:
            final.append(s)
    return final


def split(src: str, pace: float, outdir: str, unit: str = "char"):
    os.makedirs(outdir, exist_ok=True)
    for f in glob.glob(f"{outdir}/seg*.txt"):
        os.remove(f)

    paras = []
    for line in open(src, encoding="utf-8"):
        s = line.strip()
        if not s or s.startswith(("#", ">")) or s == "---":
            continue
        paras.append(s)

    if not paras:
        print(f"[✗] 剥完 markdown 后没有正文，检查文稿：{src}")
        return 1

    target = int(MAX_SEC * pace)   # 修复点 1：满段刚好不撞 120s 上限
    floor = int(MIN_SEC * pace)    # 修复点 2：低于此量就合并

    # 修复点 3：超长自然段先按句号/逗号拆开（文档规则 6，旧内联脚本漏了）
    paras = [x for p in paras for x in split_long(p, target, unit)]

    # 贪心合并自然段
    segs, cur = [], ""
    for p in paras:
        if not cur:
            cur = p
        elif measure(cur, unit) + measure(p, unit) <= target:
            cur += p
        else:
            segs.append(cur)
            cur = p
    if cur:
        segs.append(cur)

    # 修复点 2：过短段并回相邻段，而不是拉长到 30s
    merged = []
    for s in segs:
        if merged and measure(s, unit) < floor \
                and measure(merged[-1], unit) + measure(s, unit) <= target:
            merged[-1] += s
        else:
            merged.append(s)
    # 尾部残留的短段往前并，装不下就保留（比拉慢语速好）
    if len(merged) > 1 and measure(merged[-1], unit) < floor:
        tail = merged.pop()
        if measure(merged[-1], unit) + measure(tail, unit) <= target:
            merged[-1] += tail
        else:
            merged.append(tail)

    manifest, total, clipped = {}, 0, []
    for i, s in enumerate(merged, 1):
        raw = round(measure(s, unit) / pace)
        d = min(MAX_SEC, max(MIN_SEC, raw))
        if d != raw:
            clipped.append((i, raw, d))
        manifest[f"seg{i:02d}"] = d
        total += d
        open(f"{outdir}/seg{i:02d}.txt", "w", encoding="utf-8").write(s)

    json.dump(manifest, open(f"{outdir}/manifest.json", "w"),
              ensure_ascii=False, indent=1)

    body = "".join(merged)
    n_char, n_han = len(body), len(HAN.findall(body))
    print(f"段数 {len(merged)}，总时长 {total}s = {total//60}分{total%60}秒")
    print(f"正文：字符 {n_char} / 汉字 {n_han}"
          f"（标点占 {(1-n_han/n_char)*100:.1f}%）")
    print(f"真实语速：{n_han/total:.2f} 汉字/秒 = {n_han/total*60:.0f} 汉字/分钟"
          f"　|　{n_char/total:.2f} 字符/秒")
    print(f"口径 unit={unit}　PACE={pace}　TARGET={target}字/段")
    if clipped:
        print(f"[!] {len(clipped)} 段撞上 {MIN_SEC}-{MAX_SEC}s 边界被 clip"
              f"（语速会失真）：")
        for i, raw, d in clipped[:10]:
            print(f"    seg{i:02d} {raw}s → {d}s")
    else:
        print("[✓] 无 clip，所有段语速一致")
    return 0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    unit = "han" if "--unit" in sys.argv and "han" in sys.argv[sys.argv.index("--unit") + 1] else "char"
    if len(args) < 3:
        print(__doc__)
        return 1
    return split(args[0], float(args[1]), args[2], unit)


if __name__ == "__main__":
    sys.exit(main())
