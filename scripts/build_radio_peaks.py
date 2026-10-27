#!/usr/bin/env python3
"""把 ep01.cues.json + 音频真实包络，输出成前端直接吃的 data/ep01.js。

波形不造假：从成品 m4a 解出 8k 单声道，按 140 个桶算 RMS，归一化后给前端画柱子。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "web/private-radio/media"
OUT = ROOT / "web/private-radio/data/ep01.js"
BUCKETS = 84
SR = 8000


def main() -> int:
    slug = sys.argv[1] if len(sys.argv) > 1 else "ep01"
    cues_path = MEDIA / f"{slug}.cues.json"
    audio_path = MEDIA / f"{slug}.m4a"
    meta = json.loads(cues_path.read_text(encoding="utf-8"))

    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(audio_path), "-ac", "1", "-ar", str(SR),
         "-f", "s16le", "-"],
        capture_output=True,
    )
    if raw.returncode != 0:
        raise SystemExit(raw.stderr.decode()[-500:])

    import numpy as np

    x = np.frombuffer(raw.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    size = len(x) // BUCKETS
    peaks = []
    for i in range(BUCKETS):
        seg = x[i * size:(i + 1) * size]
        peaks.append(float(np.sqrt((seg ** 2).mean())) if len(seg) else 0.0)
    top = max(peaks) or 1.0
    peaks = [round(min(1.0, (p / top) ** 0.62), 3) for p in peaks]

    payload = {
        "slug": slug,
        "chars": meta.get("chars", 0),
        "duration": round(len(x) / SR, 2),
        "cues": meta["cues"],
        "peaks": peaks,
    }
    OUT.write_text(
        "/* 由 scripts/build_radio_peaks.py 生成，别手改 */\n"
        "window.EPISODE = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"[✓] {OUT}  {payload['duration']}s  {len(payload['cues'])} 段  {len(peaks)} 柱")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
