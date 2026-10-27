#!/usr/bin/env python3
"""私台 · 成品音频构建。

把 content/<slug>.txt 的一行一段，按段合成、按段计时，最后并成一条 m4a，
同时吐出一份 cues.json（每段的起止秒），前端据此做逐段跟读高亮。

要点：
- 音色**必须**用固定预设（provider `mimo_tts`）。音色设计（voicedesign）每次调用
  都可能换一把嗓子，跨段会听出是同一个人还是三个人——2026-10-24 实测频谱重心
  1850 / 3429 / 1910 Hz，不能用。
- 段间留 PAD 秒静音，给播客留呼吸，也让高亮切换不贴脸。
- 段级 wav 落盘可续跑：中途断了重跑只补缺的段。

用法:
    python3 scripts/build_radio_audio.py web/private-radio/content/ep01.txt
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import cloud_tts  # noqa: E402

PAD = 0.28           # 段间静音（秒）
SAMPLE_RATE = 24000  # MiMo 固定 24k 单声道


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / float(w.getframerate())


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"命令失败: {' '.join(cmd[:8])}\n{proc.stderr[-600:]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("text_file")
    ap.add_argument("--provider", default="mimo_tts")
    ap.add_argument("--slug", default="")
    ap.add_argument("--out-dir", default="")
    args = ap.parse_args()

    src = Path(args.text_file).resolve()
    slug = args.slug or src.stem
    out_dir = Path(args.out_dir) if args.out_dir else PROJECT_ROOT / "web/private-radio/media"
    out_dir.mkdir(parents=True, exist_ok=True)
    seg_dir = PROJECT_ROOT / "output/audio" / f".radio-seg-{slug}"
    seg_dir.mkdir(parents=True, exist_ok=True)

    lines = [ln.strip() for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip()]
    cfg = cloud_tts.get_provider_config(args.provider)
    print(f"[i] {len(lines)} 段 · provider={args.provider} · model={cfg.get('model')}")

    cues, timelines = [], []
    cursor = 0.0
    for idx, text in enumerate(lines, start=1):
        seg = seg_dir / f"{idx:03d}.wav"
        if not seg.exists() or seg.stat().st_size < 2000:
            cloud_tts.synthesize_with_config(args.provider, cfg, text, seg)
            print(f"  [{idx:02d}/{len(lines)}] 合成 {wav_seconds(seg):5.2f}s  {text[:22]}…")
        else:
            print(f"  [{idx:02d}/{len(lines)}] 复用 {wav_seconds(seg):5.2f}s")
        dur = wav_seconds(seg)
        cues.append({
            "i": idx,
            "start": round(cursor, 3),
            "end": round(cursor + dur, 3),
            "text": text,
        })
        timelines.append(seg)
        cursor += dur + PAD

    # 拼接：每段后补 PAD 静音
    concat_list = seg_dir / "concat.txt"
    with concat_list.open("w", encoding="utf-8") as fh:
        for seg in timelines:
            fh.write(f"file '{seg}'\n")
            fh.write(f"file '{_silence(seg_dir, PAD)}'\n")

    m4a = out_dir / f"{slug}.m4a"
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-af", "alimiter=limit=0.891:level=disabled",
        "-ar", "24000", "-ac", "1", "-c:a", "aac", "-b:a", "64k",
        str(m4a),
    ])

    meta = {
        "slug": slug,
        "chars": len(re.findall(r"[\u4e00-\u9fff]", "\n".join(lines))),
        "duration": round(cursor - PAD, 2),
        "cues": cues,
    }
    (out_dir / f"{slug}.cues.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"[✓] {m4a}  {meta['duration'] / 60:.1f} 分钟  {meta['chars']} 汉字")
    return 0


def _silence(seg_dir: Path, seconds: float) -> Path:
    path = seg_dir / f"pad-{seconds}.wav"
    if not path.exists():
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono",
            "-t", str(seconds), "-c:a", "pcm_s16le", str(path),
        ])
    return path


if __name__ == "__main__":
    raise SystemExit(main())
