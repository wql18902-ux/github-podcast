#!/usr/bin/env python3
"""闸门层（= 生命周期钩子，设计稿 §4.5 / §4.6）。

三条纪律，改之前先读：
  1. **只读产物、只写状态**（CQRS）。验收路径绝不经过生成路径。这一点现有
     verify-episode.sh 已经做对了，继续保留。
  2. **判据全部来自 config/agent.json**。想在代码里加一条硬闸，先回答「配置里哪个键」。
     没测过正负样本的指标一律不进硬闸（项目记忆里三条作废指标就是这么来的）。
  3. **指标全是确定性的**，不引入模型评分。「讲得好不好听」没有 ground truth，
     硬做只会得到假分数——主观质量交给审稿 agent（只审可判定项）+ 人工抽听。

判据与 scripts/verify-episode.sh 逐条对齐。对齐不是抄：verify-episode.sh 仍是
「闸门唯一入口」，是它写 output/latest-status.txt（豆包那班读那个契约）。本模块的作用是
在它之外多给一份**结构化**的判决与指标，落进 SQLite，顺便在两者结论不一致时报漂移。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import paths, state, tools

# 正文汉字：与 verify-episode.sh 的 `[一-鿿]` 同口径（中日韩统一表意文字基本区）
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
# 拆解笔记字段标题：`## 1. xxx` / `## 01、xxx`
FIELD_RE = re.compile(r"^## *[0-9]+[ .、]", re.M)
# 「含具体数字的行」：两位以上数字。好样本 76 行 / 差样本 9 行，阈值取 20。
VALUE_RE = re.compile(r"[0-9]{2,}")


@dataclass
class GateResult:
    """设计稿 §6.3。detail 要能直接贴进飞书告警——说人话，别写内部变量名。"""

    name: str
    passed: bool
    detail: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    # 下面两个是实现时加的：
    #   hard=False        只提示不拦（比如「三节缺了哪一节」「时长偏差」）
    #   defer=True        整期让路，但不算失败（待消费闸：上一期还没合成，这期别写）
    hard: bool = True
    defer: bool = False

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


# ---------------------------------------------------------------- 基础读取


def _text(path: str | Path) -> str:
    p = paths.abs_path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def _han_count(text: str) -> int:
    return len(HAN_RE.findall(text))


def blacklist_entries(cfg: dict[str, Any]) -> list[str]:
    """读黑名单，剥掉行尾注释。

    这是个真修过的 bug：scripts/verify-episode.sh 原来把**整行**（含 `\\t# 官方口径…`）
    当匹配串，于是 grep -F 永远匹配不到——这条闸从立起来到 2026-09-21 之间一次都没拦过。
    （2026-09-21 用 Gemini CLI 当正样本实测确认，脚本那边已同步改掉。）
    """
    p = paths.abs_path(cfg["gates"]["script"]["blacklist_file"])
    if not p.exists():
        return []
    out: list[str] = []
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def pre_draft(date: str, cfg: dict[str, Any]) -> list[GateResult]:
    """写稿前的钩子（pre_draft）。对应事故：「拿已停服项目当现役讲」「重录上一期」。

    只做两件确定的事：黑名单文件可读、上一期稿子有没有被消费掉。
    「项目是不是重复讲过」由 episodes.log 在选料那步拦（episode.py 内部），
    这里不重复实现——同一件事两处判，迟早对不上。
    """
    results: list[GateResult] = []

    bl = blacklist_entries(cfg)
    results.append(
        GateResult(
            name="blacklist_readable",
            passed=bool(bl),
            detail=f"黑名单 {len(bl)} 条" if bl else "黑名单文件读不到或没有条目，这条闸等于没开",
            metrics={"entries": len(bl)},
        )
    )

    # 待消费闸：与 daily-prepare.sh 第 48-54 行同一套判据，只是把「最新成品」换成
    # mtime 判（不按文件名日期前缀）。
    pending = pending_synthesis(cfg)
    if pending["pending"]:
        results.append(
            GateResult(
                name="pending_synthesis",
                passed=False,
                defer=True,
                hard=False,
                detail=(
                    f"上一期还没合成音频（latest-script.md 写于 {pending['age_h']}h 前，"
                    f"最新成品 {pending['newest']}）。这期让路，不覆盖——"
                    f"一覆盖，那期稿子就永远出不来音频了。"
                ),
                metrics={"age_h": pending["age_h"]},
            )
        )
    else:
        results.append(
            GateResult(name="pending_synthesis", passed=True, detail="没有待消费的旧稿", metrics=dict(pending))
        )
    return results


def pending_synthesis(cfg: dict[str, Any]) -> dict[str, Any]:
    """上一期稿子写好了但还没合成？判据：latest-script.md 比 output/audio 里最新成品还新。

    48 小时逃生门（同 daily-prepare.sh）：豆包要是坏了好几天，不能因为一直没成品
    就把夜班永久卡死。
    """
    script = paths.LATEST_SCRIPT
    newest = tools.newest_product()
    info: dict[str, Any] = {"pending": False, "age_h": 0, "newest": newest.name if newest else None}
    if newest is None or not script.exists():
        return info
    if script.stat().st_mtime <= newest.stat().st_mtime:
        return info
    age_h = int((state_time() - script.stat().st_mtime) // 3600)
    status_first = ""
    if paths.LATEST_STATUS.exists():
        status_first = paths.LATEST_STATUS.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
        status_first = status_first[0] if status_first else ""
    info["age_h"] = age_h
    # 48h 内 + 状态是 OK 才算「待消费」；状态非 OK 说明上一期本来就失败了，不占位。
    info["pending"] = age_h < 48 and status_first.startswith("OK")
    return info


def state_time() -> float:
    """单独包一层是为了测试能打桩。"""
    import time

    return time.time()


# ---------------------------------------------------------------- 内容闸 + 时长闸


def pre_synthesis(date: str, cfg: dict[str, Any]) -> list[GateResult]:
    """合成前全套闸门。逐条对齐 scripts/verify-episode.sh 的 A / B 两段。

    顺序有讲究：内容闸（读没读到实现级）先跑，因为「没读源码」比「写得短」更根本。
    """
    g = cfg["gates"]
    bcfg, scfg, lcfg = g["breakdown"], g["script"], g["length"]
    script = paths.LATEST_SCRIPT
    breakdown = paths.date_paths(date)["breakdown"]
    results: list[GateResult] = []

    # --- A 内容闸 ---
    s_text = _text(script)
    results.append(
        GateResult(
            name="script_exists",
            passed=bool(s_text),
            detail=f"{paths.rel(script)} 在" if s_text else f"没产出 {paths.rel(script)}",
        )
    )
    b_text = _text(breakdown)
    results.append(
        GateResult(
            name="breakdown_exists",
            passed=bool(b_text),
            detail=f"{paths.rel(breakdown)} 在" if b_text else f"没写拆解笔记 {paths.rel(breakdown)}（跳过了逐文件读源码那步）",
        )
    )
    if not b_text:
        # 笔记都没有，后面的字段/字节/节数没意义，直接返回（别报五条同样的失败）
        return results

    fields = len(FIELD_RE.findall(b_text))
    results.append(
        GateResult(
            name="breakdown_fields",
            passed=fields >= bcfg["min_fields"],
            detail=f"拆解笔记 {fields} 个字段标题（需 {bcfg['min_fields']}）"
            + ("" if fields >= bcfg["min_fields"] else "，疑似没逐字段填"),
            metrics={"fields": fields, "need": bcfg["min_fields"]},
        )
    )

    n_bytes = len(b_text.encode("utf-8"))
    results.append(
        GateResult(
            name="breakdown_bytes",
            passed=n_bytes >= bcfg["min_bytes"],
            detail=f"拆解笔记 {n_bytes} 字节（需 {bcfg['min_bytes']}）"
            + ("" if n_bytes >= bcfg["min_bytes"] else "，拆得太浅"),
            metrics={"bytes": n_bytes, "need": bcfg["min_bytes"]},
        )
    )

    sections = bcfg["require_one_of_sections"]
    present = [
        sec
        for sec in sections
        if re.search(rf"^#+ *([0-9]+[ .、]+)?{re.escape(sec)}", b_text, re.M)
    ]
    results.append(
        GateResult(
            name="breakdown_sections",
            passed=len(present) >= 1,
            detail=(
                f"实现级节 {len(present)}/{len(sections)}：{'、'.join(present)}"
                if present
                else f"「{' / '.join(sections)}」三节一节都没有——没有实现级内容"
            ),
            metrics={"present": present, "missing": [s for s in sections if s not in present]},
        )
    )

    value_lines = len([ln for ln in b_text.splitlines() if VALUE_RE.search(ln)])
    results.append(
        GateResult(
            name="breakdown_value_lines",
            passed=value_lines >= bcfg["min_value_lines"],
            detail=f"拆解笔记 {value_lines} 行含具体数字（需 {bcfg['min_value_lines']}，好样本 76 / 差样本 9）"
            + ("" if value_lines >= bcfg["min_value_lines"] else "——供料还是架构级"),
            metrics={"value_lines": value_lines, "need": bcfg["min_value_lines"]},
        )
    )

    # --- 时效闸：只拦真缺项，不判内容质量 ---
    if scfg["require_info_deadline"]:
        miss: list[str] = []
        if not re.search(r"信息截止[:：]", s_text):
            miss.append(f"稿子 {paths.rel(script)} 开头没写「信息截止：YYYY-MM-DD」")
        if not re.search(r"信息截止", b_text):
            miss.append("拆解笔记缺「信息截止」栏")
        if not re.search(r"当前版本", b_text):
            miss.append("拆解笔记缺「当前版本」栏")
        results.append(
            GateResult(
                name="info_deadline",
                passed=not miss,
                detail="；".join(miss) if miss else "时效两栏齐（信息截止 / 当前版本）",
            )
        )

    # --- 黑名单闸：只看稿子开头 N 行 ---
    # 讲现役拆解时项目名一定出现在标题区；正文里顺带对比、笔记里附录留档都允许。
    head_n = scfg["blacklist_head_lines"]
    head = "\n".join(s_text.splitlines()[:head_n]).lower()
    hits = [p for p in blacklist_entries(cfg) if p.lower() in head]
    results.append(
        GateResult(
            name="blacklist",
            passed=not hits,
            detail="稿子开头没有黑名单项目" if not hits else f"稿子开头出现黑名单项目「{hits[0]}」（已被取代或停服，不许做现役拆解）",
            metrics={"hits": hits, "head_lines": head_n},
        )
    )

    # --- B 时长闸 ---
    han = _han_count(s_text)
    cpm = lcfg["chars_per_minute"]
    est = round(han / cpm, 1)
    short = lcfg["fail_below_chars"] <= han < lcfg["min_chars"]
    results.append(
        GateResult(
            name="chars",
            passed=han >= lcfg["fail_below_chars"],
            detail=(
                f"正文 {han} 汉字 ≈{est:.0f} 分钟"
                + ("" if not short else f"（低于目标 {lcfg['min_chars']}，放行但标 SHORT——宁可短也不让当夜没稿）")
                + ("" if han >= lcfg["fail_below_chars"] else f"，远低于一期正常量（<{lcfg['fail_below_chars']}），拆得太浅")
            ),
            metrics={"chars": han, "est_minutes": est, "short": short, "min_chars": lcfg["min_chars"]},
        )
    )
    return results


def pre_upload(path: str | Path, cfg: dict[str, Any], *, est_minutes: float | None = None) -> list[GateResult]:
    """上传前的钩子：拦「上传半截文件」。

    设计稿 §12.2 说过：豆包那班可见性为零，它跑了一半失败留下半截文件，外环可能
    误判成功。这两条检查（大小 + 时长）就是缓解手段，能降噪但治不了根。
    """
    pcfg = cfg["gates"].get("product", {})
    min_bytes = int(pcfg.get("min_bytes", 1_000_000))
    min_minutes = float(pcfg.get("min_minutes", 20))
    results: list[GateResult] = []

    p = paths.abs_path(path)
    exists = p.exists()
    size = p.stat().st_size if exists else 0
    results.append(
        GateResult(
            name="product_exists",
            passed=exists and size >= min_bytes,
            detail=f"{paths.rel(p)} {size/1048576:.1f} MB" if exists else f"产物不存在：{paths.rel(p)}",
            metrics={"bytes": size, "min_bytes": min_bytes},
        )
    )
    if not exists:
        return results

    minutes = tools.probe_duration(p)
    if minutes is None:
        # 量不到不拦（ffprobe 缺失 / 编码怪），只提示。诚实边界写清楚。
        results.append(
            GateResult(
                name="product_duration",
                passed=True,
                hard=False,
                detail="ffprobe 量不到时长，未确认（不拦，只记录）",
            )
        )
        return results

    ok_len = minutes >= min_minutes
    results.append(
        GateResult(
            name="product_duration",
            passed=ok_len,
            detail=f"实测 {minutes:.1f} 分钟（下限 {min_minutes:.0f}）"
            + ("" if ok_len else "，疑似半截文件"),
            metrics={"actual_minutes": round(minutes, 2), "min_minutes": min_minutes},
        )
    )

    lo, hi = cfg["gates"]["length"]["duration_ratio_accept"]
    if est_minutes:
        ratio = minutes / est_minutes
        inside = lo <= ratio <= hi
        results.append(
            GateResult(
                name="duration_ratio",
                passed=inside,
                hard=False,     # 只告警不拦：语速有正常散布，硬卡会误伤
                detail=(
                    f"实测 {minutes:.0f} 分 / 推算 {est_minutes:.0f} 分 = {ratio:.2f}"
                    + ("" if inside else f"，超出容许区间 {lo}-{hi}（防「稿子写够了但音频只有 20 分钟」）")
                ),
                metrics={"ratio": round(ratio, 3), "accept": [lo, hi]},
            )
        )
    return results


def pre_synth(date: str, cfg: dict[str, Any]) -> list[GateResult]:
    """降级到本地合成之前的钩子。跟 pre_synthesis 不同：这里产物还没生成，
    要判的是「值不值得占用本机两小时」。"""
    first = _status_first()
    max_age_h = float(cfg["synth"].get("script_max_age_h", 12))
    age_h = None
    if paths.LATEST_SCRIPT.exists():
        age_h = (state_time() - paths.LATEST_SCRIPT.stat().st_mtime) / 3600

    results = [
        GateResult(
            name="status_ok",
            passed=first.startswith("OK"),
            detail="latest-status.txt 首行 OK" if first.startswith("OK") else f"状态不是 OK：{first[:80]}",
        ),
        GateResult(
            name="has_script",
            passed=paths.LATEST_SCRIPT.exists(),
            detail=f"稿子在：{paths.rel(paths.LATEST_SCRIPT)}" if paths.LATEST_SCRIPT.exists() else "没有 latest-script.md，降级合成没东西可合",
        ),
        GateResult(
            name="script_fresh",
            passed=(age_h is not None and age_h <= max_age_h),
            detail=(
                f"稿子 {age_h:.0f} 小时前落的（上限 {max_age_h:.0f}h）" if age_h is not None
                else "稿子不存在，算不新鲜"
            )
            + ("" if (age_h is not None and age_h <= max_age_h) else "——超龄合成等于把上一期重录一遍，拦"),
            metrics={"script_age_h": round(age_h, 1) if age_h is not None else None},
        ),
    ]
    return results


def _status_first() -> str:
    if not paths.LATEST_STATUS.exists():
        return ""
    lines = paths.LATEST_STATUS.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[0] if lines else ""


# ---------------------------------------------------------------- 汇报


def passed_all(results: Iterable[GateResult]) -> bool:
    return all(r.passed for r in results if r.hard)


def defer_requested(results: Iterable[GateResult]) -> GateResult | None:
    for r in results:
        if r.defer:
            return r
    return None


def format_failure(results: Iterable[GateResult]) -> str:
    """把没过闸的项拼成一段能直接喂回写稿 agent 的修改指令（设计稿 §6.3）。

    刻意的写法要求：每条都带**具体数字与期望值**，不许只说「不够」——
    写稿 agent 要照它补料，说「太浅」它不知道该补多少。
    """
    bad = [r for r in results if not r.passed and r.hard]
    soft = [r for r in results if not r.passed and not r.hard]
    if not bad and not soft:
        return ""
    lines = ["验收闸没过，按下面逐条补，补完重跑 `bash scripts/verify-episode.sh`：", ""]
    for r in bad:
        lines.append(f"[必须修] {r.name}：{r.detail}")
    for r in soft:
        lines.append(f"[提示]   {r.name}：{r.detail}")
    return "\n".join(lines)


def report(date: str, cfg: dict[str, Any], conn=None) -> str:
    """人话版一期体检报告：各指标 + 与上一期对比 + 是否退化（设计稿 §4.6）。"""
    results = pre_synthesis(date, cfg)
    lines = [f"===== 第 {date} 期体检 ====="]
    for r in results:
        mark = "✓" if r.passed else ("–" if not r.hard else "✗")
        lines.append(f" {mark} {r.name}: {r.detail}")

    chars_gate = next((r for r in results if r.name == "chars"), None)
    if conn is not None:
        ep = state.current_episode(conn, date)
        prev = state.previous_episode(conn, date)
        if ep is None:
            lines.append("")
            lines.append("（库里还没有这一期的记录，用 `python3 -m agent.cli run` 建）")
        else:
            lines.append("")
            lines.append(f"库：ep{ep.ep_no} stage={ep.stage} status={ep.status} attempt={ep.attempt} 审稿轮={ep.review_round}")
        if prev and chars_gate:
            prev_chars = prev.chars or 0
            now_chars = chars_gate.metrics.get("chars", 0)
            delta = now_chars - prev_chars
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
            lines.append(
                f"对比上一期（{prev.date}，{prev_chars} 汉字）：{now_chars} 汉字，{arrow}{abs(delta)}"
            )
            if prev_chars and delta < 0 and abs(delta) / prev_chars > 0.15:
                lines.append(" [!] 比上期少 15% 以上，疑似退化——看是不是少读了文件（files_read）")
    return "\n".join(lines)


def gate_metrics(results: Iterable[GateResult]) -> dict[str, Any]:
    """把各闸的 metrics 摊平，方便一次塞进 episodes 表。"""
    out: dict[str, Any] = {}
    for r in results:
        out.update({k: v for k, v in r.metrics.items() if not isinstance(v, (list, dict))})
    return out


def gate_json(results: Iterable[GateResult]) -> str:
    return json.dumps([r.as_dict() for r in results], ensure_ascii=False)
