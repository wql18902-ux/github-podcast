#!/usr/bin/env python3
"""整期合成：MiMo-V2.5-TTS-VoiceClone（云 API + 克隆音色）。

跟 scripts/tts_local.py（本地 VoxCPM2）并列的第二条整期合成路线：
- 音色走 `mimo-v2.5-tts-voiceclone`，参考音频按 Data URL 传给小米接口
- 不需要本地 GPU / llama-tts-server，纯 HTTP，段与段之间可断点续跑
- 产物 output/audio/<日期>-ep<N>-mimo.m4a（文件名带 -mimo，跟豆包和 -local 都不撞）

用法:
    python3 scripts/tts_mimo.py                                   # 当天稿件，默认参考音
    python3 scripts/tts_mimo.py --limit 2                         # 只合前 2 段试听
    python3 scripts/tts_mimo.py --ref voices/另一把嗓子.wav         # 临时换克隆参考音
    python3 scripts/tts_mimo.py --input output/xxx-script.md --output /tmp/x.m4a

流程: 剥 markdown → 按句分段(≤--max-chars) → 逐段调 MiMo(失败自动重试) →
      落段级 wav（可续跑）→ ffmpeg 拼接 → 限幅 -1.5 dBTP → m4a。

参考音频默认 voices/mimo-clone-ref.wav —— 这是**王振宇的克隆音色**（25 秒，2026-10-07
从他的公开音频 19:55 处切出转 24k 单声道；包络相关 0.9999 已证同源，取证见 voices/README.md）。
两条线共用这一把嗓子：每日流水线、以及 output/wang-style/ 那条王振宇风格试播线。
**拿合成出来的音频当参考 = 二次克隆，音质会掉一层**，要换嗓子请换人声原音。
**用别人的声音做内容，成品音频必须标明 AI 合成**。

Key 只从 macOS Keychain 读（service ai-jarvis-tts-console，account mimo_api），
本脚本不碰任何密钥文件。接口层 cloud_tts._opener() 显式直连，绕过失效的 7890 代理。
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import cloud_tts  # noqa: E402
from tts_local import HAN, atempo_chain, split_sentences, strip_markdown, wav_duration  # noqa: E402

DEFAULT_PROVIDER = "mimo_tts_clone"
DEFAULT_REF = PROJECT_ROOT / "voices" / "mimo-clone-ref.wav"
SAMPLE_RATE = 24000  # MiMo 返回 24kHz 单声道 wav，拼接前统一到这个规格
RETRIES = 3
# 输出侧保险丝（跟 tts_local.py 同一条）：只削峰，不动整体响度
ALIMITER = "alimiter=limit=0.8414:level=disabled"


def run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"命令失败({proc.returncode}): {' '.join(args[:6])}…\n{proc.stderr[-800:]}"
        )


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        text=True,
    ).strip()
    return float(out)


def normalize_wav(src: Path, dst: Path) -> None:
    """每段落到同一规格（24k 单声道 PCM16），拼接才敢用 -c copy。"""
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(dst)])


def synth_one(provider: str, cfg: dict, text: str, out: Path) -> Path:
    """调一次 MiMo；网络/限流抖动自动退避重试。"""
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            return cloud_tts.synthesize_with_config(provider, cfg, text, out)
        except Exception as exc:  # noqa: BLE001 —— 云 API 什么错都可能抛，重试后统一抛
            last = exc
            if attempt < RETRIES:
                wait = 2 * attempt
                print(f"[!] 第 {attempt}/{RETRIES} 次失败({exc})，{wait}s 后重试",
                      file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"连续 {RETRIES} 次合成失败: {last}")


def build_cfg(provider: str, ref: Path, style: str) -> dict:
    cfg = cloud_tts.get_provider_config(provider)
    if not cloud_tts.has_provider_secret(provider):
        raise SystemExit(
            f"[✗] {provider} 还没有保存 API Key（Keychain service "
            f"ai-jarvis-tts-console）——先去控制台存一次，或 "
            f"python3 scripts/cloud_tts.py set-secret {provider}"
        )
    model = str(cfg.get("model") or "")
    if not model.endswith("-voiceclone"):
        raise SystemExit(
            f"[✗] {provider} 的模型是 {model or '空'}，不是 voiceclone。"
            f"整期克隆路线要 mimo_tts_clone（mimo-v2.5-tts-voiceclone）"
        )
    extra = dict(cfg.get("extra") or {})
    extra["reference_audio_path"] = str(ref.relative_to(PROJECT_ROOT))
    extra["style_prompt"] = style
    cfg["extra"] = extra
    return cfg


def segment_dir(output: Path, date: str, input_path: Path) -> Path:
    """段级 wav 放哪儿。

    三个条件都不能少：
    1. 必须在 `output/audio/` 下（那个目录已在 .gitignore 里）；
    2. 必须是隐藏目录——`local-fallback.sh` 和 `agent.tools.newest_product` 都按
       `output/audio/*.m4a` + `is_file()` 找成品，隐藏目录扫不到，不会把半截段当成品；
    3. **必须带稿件内容哈希**。只按日期算是 2026-10-07 踩过的坑：同一天换一份稿子，
       旧段还在，续跑逻辑直接跳过合成，把上一份的音频拼进这一份——不报错，只是成品是错的。

    换了稿子 → 新目录、全量重合成；同一份稿子重跑 → 跳过已合成的段。
    """
    digest = hashlib.sha1(input_path.read_bytes()).hexdigest()[:8]
    return output.parent / f".mimo-seg-{date}-{digest}"


def write_concat_list(segments: list[Path], list_file: Path) -> Path:
    """写 ffmpeg concat 的清单文件。

    ⚠️ 必须写**绝对路径**：concat demuxer 把清单里的相对路径解析成
    「相对清单文件所在目录」，不是相对当前工作目录。2026-10-07 踩过：输出给
    相对路径（output/...）时段路径被拼成 `<段目录>/output/<段目录>/seg001.ok.wav`，
    直接 No such file or directory。冒烟测试全用 /tmp 绝对路径才没暴露——
    `pipeline.sh synth-mimo` 一跑就中，所以这里有测试钉住。
    """
    lines = []
    for p in segments:
        assert p.is_file(), f"段文件不在: {p}"
        lines.append(f"file '{p.resolve()}'\n")
    list_file.write_text("".join(lines), encoding="utf-8")
    return list_file


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=PROJECT_ROOT / "output" / "latest-script.md")
    ap.add_argument("--output", type=Path, default=None,
                    help="成品 m4a 路径；默认 output/audio/<日期>-ep<N>-mimo.m4a")
    ap.add_argument("--provider", default=DEFAULT_PROVIDER)
    ap.add_argument("--ref", type=Path, default=DEFAULT_REF,
                    help="克隆参考音频（人声原音，项目目录内）")
    ap.add_argument("--style", default="",
                    help="可选：风格指令（透传给 MiMo user 消息）；默认空 = 跟着参考音频")
    ap.add_argument("--max-chars", type=int, default=400,
                    help="每段最多字符数（默认 400，约 2 分钟音频；调小＝失败重跑更省）")
    ap.add_argument("--han-per-min", type=float, default=0,
                    help="按汉字/分钟定标（atempo，不变调）。0=原速（默认）。"
                         "实测 MiMo 克隆链路原速 257-317 汉字/分（三段样本）；"
                         "想要本地 VoxCPM2 那档约 187 就传 187")
    ap.add_argument("--limit", type=int, default=0, help="只合成前 N 段（试听）")
    ap.add_argument("--fresh", action="store_true", help="清掉旧段级 wav 重新合成")
    args = ap.parse_args()

    if shutil.which("ffmpeg") is None:
        raise SystemExit("[✗] 找不到 ffmpeg")
    ref = args.ref if args.ref.is_absolute() else PROJECT_ROOT / args.ref
    ref = ref.resolve()
    if not ref.is_file():
        raise SystemExit(f"[✗] 参考音频不存在: {ref}")
    try:
        ref.relative_to(PROJECT_ROOT)
    except ValueError:
        raise SystemExit(f"[✗] 参考音频必须在项目目录内: {ref}")
    if not args.input.is_file():
        raise SystemExit(f"[✗] 输入不存在: {args.input}")

    cfg = build_cfg(args.provider, ref, args.style)

    date = time.strftime("%Y-%m-%d")
    if args.output is None:
        ep_n = subprocess.check_output(
            ["python3", str(PROJECT_ROOT / "scripts" / "ep_no.py")], text=True
        ).strip()
        args.output = PROJECT_ROOT / "output" / "audio" / f"{date}-ep{ep_n}-mimo.m4a"

    text = strip_markdown(args.input.read_text(encoding="utf-8"))
    if not text:
        raise SystemExit("[✗] 剥完 markdown 后没有正文")
    segments = split_sentences(text, args.max_chars)
    if args.limit:
        segments = segments[: args.limit]

    workdir = segment_dir(args.output, date, args.input)
    if args.fresh and workdir.is_dir():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    han_total = len(HAN.findall("".join(segments)))
    print(f"[*] {len(segments)} 段 / 汉字 {han_total} / 参考音频 {ref.name}"
          f"（{ffprobe_duration(ref):.1f}s） / provider {args.provider}")
    print(f"[*] 段级目录 {workdir}（已有段自动跳过，删它或 --fresh 才重跑）")

    done = []
    for i, seg in enumerate(segments, 1):
        raw = workdir / f"seg{i:03d}.wav"
        final = workdir / f"seg{i:03d}.ok.wav"
        if final.exists() and final.stat().st_size > 44:
            done.append(final)
            print(f"[{i}/{len(segments)}] 已存在，跳过")
            continue
        tmp = workdir / f"seg{i:03d}.raw.wav"
        synth_one(args.provider, cfg, seg, tmp)
        normalize_wav(tmp, final)
        tmp.unlink(missing_ok=True)
        done.append(final)
        print(f"[{i}/{len(segments)}] {len(seg)} 字 -> {wav_duration(final):.1f}s")

    list_file = workdir / "list.txt"
    # 段路径一律转绝对（ffmpeg concat 的解析规则见 write_concat_list 的注释）。
    list_file = write_concat_list(done, workdir / "list.txt")
    merged = workdir / "full.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(list_file), "-c", "copy", str(merged)])
    secs_merged = ffprobe_duration(merged)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    filters = []
    if args.han_per_min > 0:
        # 实测原速 257-317 汉字/分（三段样本），比本地 VoxCPM2（187）快一截；
        # 想跟本地那档一致就传 187。atempo 只改速度不改音高。
        target_secs = han_total / (args.han_per_min / 60.0)
        filters.append(atempo_chain(secs_merged / target_secs))
    filters.append(ALIMITER)
    run(["ffmpeg", "-y", "-v", "error", "-i", str(merged),
         "-ar", str(SAMPLE_RATE), "-ac", "1", "-b:a", "64k",
         "-filter:a", ",".join(filters), str(args.output)])

    secs = ffprobe_duration(args.output)
    minutes = secs / 60
    # 项目验收口径：正文汉字 ÷ 175 ≈ 音频分钟（见 CLAUDE.md 验收口径表）
    expect = han_total / 175
    pace = han_total / minutes if minutes else 0
    print(f"[✓] 完成 {args.output}")
    print(f"    实测 {secs:.0f}s = {minutes:.1f} 分钟 · {pace:.0f} 汉字/分"
          f"（项目换算口径预估 {expect:.1f} 分钟"
          + (f"，已按 {args.han_per_min:.0f} 汉字/分定标" if args.han_per_min > 0 else "")
          + "）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[!] 手动中断——已合成的段都留着，重跑同一条命令会接着来", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        print(f"[✗] {exc}", file=sys.stderr)
        sys.exit(1)
