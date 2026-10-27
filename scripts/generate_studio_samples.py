#!/usr/bin/env python3
"""Generate original MiMo voice-design auditions for the local studio. No cloning."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import cloud_tts

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "library"
TEXT = "你有没有读过这样一本书？合上时觉得很有道理，过了几天，却只记得它的封面。也许我们缺的，不是更多内容，而是一次属于自己的对话。把那个没想明白的问题说出来，让不同的观点碰一碰。听完以后，留下一页笔记，再和过去的想法连起来。下一次打开它，你会发现，好奇心已经有了自己的形状。这里是页声。这段声音由人工智能合成。"
VOICES = [
    ("mimo-warm", "松弛男声", "像朋友陪你读书", "成年中文男声，中低音区，音色干净温暖，松弛自然，亲近但不耳语。像坐在窗边面对一位朋友聊天，清楚地说普通话。语速从容但不拖沓，句间有自然呼吸。不要广播腔，不要夸张煽情，不加背景音乐。"),
    ("mimo-clear", "清透女声", "清楚，也有一点好奇", "成年中文女声，音色清透、柔和，有温度，声音有自然的空气感但不气声。像一位思路清晰的朋友陪你聊一本书，说普通话，语速适中。问句有一点自然的好奇，陈述句平实。不要广告腔，不要戏剧化，不加背景音乐。"),
]


def ensure_dir(path: Path) -> None:
    """沙箱里 Path.mkdir(exist_ok=True) 对已存在目录会抛 EEXIST，先判断。"""
    if not path.is_dir():
        path.mkdir(parents=True, exist_ok=True)


def main():
    media = WEB / "media"
    ensure_dir(media)
    auditions = []
    for ident, name, subtitle, direction in VOICES:
        wav = ROOT / "_tmp" / "studio-mimo-polish" / (ident + ".wav")
        ensure_dir(wav.parent)
        cfg = cloud_tts.get_provider_config("mimo_tts_design")
        cfg["model"] = "mimo-v2.5-tts-voicedesign"
        cfg.setdefault("extra", {})["style_prompt"] = direction
        cloud_tts.synthesize_with_config("mimo_tts_design", cfg, TEXT, wav)
        target = media / (ident + ".m4a")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af", "alimiter=limit=0.8414:level=disabled", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(target)], check=True)
        seconds = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(target)], text=True))
        auditions.append({"id": ident, "name": name, "subtitle": subtitle, "title": "把一本书，听成自己的问题", "src": "media/" + target.name, "seconds": round(seconds, 2), "model": cfg["model"], "provider": "MiMo", "text": TEXT, "direction": direction, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
        print(f"Generated {ident}: {seconds:.1f}s", flush=True)
    pack = {"generatedAt": datetime.now(timezone.utc).isoformat(), "aiGenerated": True, "voiceCloning": False, "items": auditions}
    (media / "mimo-auditions.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2))
    (WEB / "data" / "auditions.js").write_text("window.AUDITIONS = " + json.dumps(pack, ensure_ascii=False) + ";\n")


if __name__ == "__main__":
    main()
