#!/usr/bin/env python3
"""TTS synthesizer — turns a podcast script markdown into a single mp3.

Uses the Doubao seed-tts-2.0 HTTP unidirectional API (see 豆包语音合成代码/豆包.md):
  POST https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional
  Headers: X-Api-Key (from env DOUBAO_TTS_KEY ONLY), X-Api-Resource-Id: seed-tts-2.0
  Body: req_params{text, speaker, audio_params{format: mp3, sample_rate: 24000}}
  Response: chunked JSON lines, base64 audio in .data, code 20000000 = finished.

The API key is read from the DOUBAO_TTS_KEY environment variable only.
It is never written to any file and never printed in logs.

Note: the shell env carries a dead proxy (127.0.0.1:7890), so requests
runs with trust_env=False. See BLOCKED.md.

Usage:
  python3 scripts/tts.py --input output/latest-script.md \
      --output output/audio/<项目名>-播客完整版-<时长>min.mp3 [--speaker zh_female_vv_uranus_bigtts]
"""

import argparse
import base64
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

URL = "https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional"
RESOURCE_ID = "seed-tts-2.0"
DEFAULT_SPEAKER = "zh_female_vv_uranus_bigtts"
DONE_CODE = 20000000

# Retries for transient network failures per segment.
RETRIES = 3


def load_text(md_path: Path) -> str:
    """Read the script and strip markdown so only spoken text remains."""
    text = md_path.read_text(encoding="utf-8")
    lines = []
    for line in text.splitlines():
        if line.strip().startswith("#"):  # section headers — not spoken
            continue
        if line.strip() == "（完）":
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)      # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # links -> label
    text = text.replace("**", "").replace("*", "")
    return text.strip()


def split_sentences(text: str, max_len: int = 120):
    """Split into sentence segments; merge short ones so each request carries
    enough context for natural pacing, but never exceed ~max_len chars."""
    raw = re.split(r"(?<=[。！？；])", text)
    raw = [s.strip().replace("\n", "") for s in raw if s.strip()]
    segments, buf = [], ""
    for s in raw:
        if len(buf) + len(s) <= max_len:
            buf += s
        else:
            if buf:
                segments.append(buf)
            # a single overlong sentence gets hard-split on commas
            while len(s) > max_len:
                cut = s.rfind("，", 0, max_len)
                cut = cut if cut > 20 else max_len
                segments.append(s[:cut])
                s = s[cut:]
            buf = s
    if buf:
        segments.append(buf)
    return segments


def synthesize_segment(session, api_key, speaker, seg, index, total):
    payload = {
        "req_params": {
            "text": seg,
            "speaker": speaker,
            "audio_params": {"format": "mp3", "sample_rate": 24000},
        }
    }
    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": RESOURCE_ID,
        "Content-Type": "application/json",
        "Connection": "keep-alive",
    }
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            resp = session.post(URL, headers=headers, json=payload,
                                stream=True, timeout=120)
            if resp.status_code != 200:
                # redacted body: never echo anything that could echo the key
                raise RuntimeError(f"HTTP {resp.status_code}")
            audio = bytearray()
            finished = False
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                data = json.loads(line)
                code = data.get("code", 0)
                if code == DONE_CODE:
                    finished = True
                    if data.get("data"):
                        audio.extend(base64.b64decode(data["data"]))
                    break
                if code != 0:
                    raise RuntimeError(f"API code {code}: {data.get('message', '')}")
                if data.get("data"):
                    audio.extend(base64.b64decode(data["data"]))
            if not audio:
                raise RuntimeError("empty audio response")
            print(f"[{index}/{total}] {len(seg)} chars -> {len(audio)/1024:.0f} KB")
            return bytes(audio)
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[{index}/{total}] attempt {attempt} failed: {e}",
                  file=sys.stderr)
            time.sleep(2 * attempt)
    raise RuntimeError(f"segment {index} failed after {RETRIES} retries: {last_err}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--speaker", default=DEFAULT_SPEAKER)
    ap.add_argument("--limit", type=int, default=0,
                    help="only synthesize first N segments (for testing)")
    ap.add_argument("--atempo", type=float, default=1.0,
                    help="post-process tempo factor via ffmpeg (e.g. 0.75 slows "
                         "speech to ~255 chars/min; pitch is preserved)")
    args = ap.parse_args()

    import os
    api_key = os.environ.get("DOUBAO_TTS_KEY", "")
    if not api_key:
        print("[!] DOUBAO_TTS_KEY 未设置（key 只从环境变量读取）", file=sys.stderr)
        sys.exit(2)

    text = load_text(Path(args.input))
    segments = split_sentences(text)
    if args.limit:
        segments = segments[: args.limit]
    total_chars = sum(len(s) for s in segments)
    print(f"[*] 共 {len(segments)} 段，{total_chars} 字，音色 {args.speaker}")

    session = requests.Session()
    session.trust_env = False  # bypass dead proxy env (see BLOCKED.md)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".part.mp3")

    total_bytes = 0
    with open(tmp_path, "wb") as f:
        for i, seg in enumerate(segments, 1):
            audio = synthesize_segment(session, api_key, args.speaker,
                                       seg, i, len(segments))
            f.write(audio)
            total_bytes += len(audio)
    tmp_path.rename(out_path)
    print(f"[✓] 合成完成：{out_path}，共 {total_bytes/1024/1024:.1f} MB")

    if args.atempo and args.atempo != 1.0:
        slowed = out_path.with_name(out_path.stem + ".slow.mp3")
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(out_path),
             "-filter:a", f"atempo={args.atempo}", "-ar", "24000",
             "-b:a", "64k", str(slowed)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            print(f"[!] ffmpeg atempo 失败: {r.stderr}", file=sys.stderr)
            sys.exit(1)
        out_path.unlink()
        slowed.rename(out_path)
        print(f"[✓] 语速调整 atempo={args.atempo} 完成：{out_path}")


if __name__ == "__main__":
    main()
