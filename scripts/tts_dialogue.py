#!/usr/bin/env python3
"""Podcastfy 风格双人对谈，复用项目 MiMo 适配器；独立试播，不写每日状态。

python3 scripts/tts_dialogue.py --input output/podcastfy-pilot/dialogue.txt \
    --output output/podcastfy-pilot/双人试播-AI合成.m4a

输入只接受成对的 <Person1>…</Person1> / <Person2>…</Person2> 标签。
设计参考和原始源码见 references/podcastfy/；本文件实现为本项目新写。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import cloud_tts
from tts_local import split_sentences
from tts_mimo import ALIMITER, ffprobe_duration, run

SAMPLE_RATE = 24000
VERSION = 1
# 仅裁掉每段两端的静音；反转后再裁开头，避免删掉句子内部的停顿。
TRIM = "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-55dB"
NORMALIZE = f"{TRIM},areverse,{TRIM},areverse,loudnorm=I=-18:TP=-2:LRA=11"
TURN_RE = re.compile(r"<Person([12])>(.*?)</Person\1>", re.DOTALL)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def parse_dialogue(text: str) -> list[dict]:
    """严格消费全文，拒绝漏标签/未知说话者，保留连续同角色与 Person2 开场。"""
    turns = []
    cursor = 0
    for match in TURN_RE.finditer(text):
        if text[cursor:match.start()].strip():
            raise ValueError("标签外有未识别内容；输入只允许 Person1/Person2 对话")
        spoken = " ".join(match[2].split())
        if not spoken or "<" in spoken or ">" in spoken:
            raise ValueError("台词为空或含嵌套标签；请只保留可以直接念的正文")
        turns.append({"speaker": f"Person{match[1]}", "text": spoken})
        cursor = match.end()
    if text[cursor:].strip() or not turns:
        raise ValueError("对话标签缺失或没有闭合")
    if {t["speaker"] for t in turns} != {"Person1", "Person2"}:
        raise ValueError("双人对话需要 Person1 和 Person2 都有台词")
    return turns


def speaker_configs(settings: dict) -> tuple[dict, dict]:
    specs = settings.get("speakers", {})
    if set(specs) != {"Person1", "Person2"}:
        raise ValueError("配置必须包含且只包含 Person1、Person2")
    configs, identities = {}, {}
    for role, spec in specs.items():
        provider = spec.get("provider")
        if provider not in {"mimo_tts", "mimo_tts_clone"}:
            raise ValueError(f"{role} 只支持现有 MiMo 预置或克隆路线")
        cfg = cloud_tts.get_provider_config(provider)
        expected = "mimo-v2.5-tts-voiceclone" if provider == "mimo_tts_clone" else "mimo-v2.5-tts"
        if cfg.get("adapter") != "mimo_tts" or cfg.get("model") != expected:
            raise ValueError(f"{role} 的 provider 未配置为 {expected}")
        extra = dict(cfg.get("extra") or {})
        extra.update(format="wav", style_prompt=str(spec.get("style", "")))
        identity = {"provider": provider, "model": cfg["model"],
                    "endpoint": cfg["endpoint"], "style": extra["style_prompt"]}
        if provider == "mimo_tts_clone":
            ref = (ROOT / spec.get("reference_audio", "")).resolve()
            if not ref.is_relative_to(ROOT) or not ref.is_file():
                raise ValueError(f"{role} 的克隆参考音必须是项目内的文件")
            extra["reference_audio_path"] = str(ref.relative_to(ROOT))
            identity.update(reference_audio=extra["reference_audio_path"],
                            reference_sha256=file_hash(ref))
        else:
            voice = str(spec.get("voice", "")).strip()
            if not voice:
                raise ValueError(f"{role} 缺少 voice")
            cfg["voice"] = voice
            identity["voice"] = voice
        cfg["extra"] = extra
        configs[role] = (provider, cfg)
        identities[role] = identity
    return configs, identities


def build_plan(text: str, settings: dict, limit: int = 0) -> tuple[dict, dict]:
    turns = parse_dialogue(text)
    if limit < 0:
        raise ValueError("limit 不能为负数")
    max_chars = settings.get("max_chars", 400)
    gap = settings.get("speaker_gap_ms", 160)
    if type(max_chars) is not int or not 50 <= max_chars <= 1200:
        raise ValueError("max_chars 必须为 50–1200 的整数")
    if type(gap) is not int or not 0 <= gap <= 2000:
        raise ValueError("speaker_gap_ms 必须为 0–2000 的整数")
    configs, identities = speaker_configs(settings)
    selected = turns[:limit] if limit else turns
    chunks = []
    for number, turn in enumerate(selected, 1):
        for part in split_sentences(turn["text"], max_chars):
            chunks.append({"turn": number, "speaker": turn["speaker"], "text": part})
    plan = {"version": VERSION, "speakers": identities, "chunks": chunks,
            "total_turns": len(turns), "selected_turns": len(selected),
            "preview": len(selected) < len(turns), "gap_ms": gap,
            "sample_rate": SAMPLE_RATE, "normalization": NORMALIZE, "limiter": ALIMITER}
    return plan, configs


def cached_wav_valid(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as wav:
            return (wav.getnchannels() == 1 and wav.getsampwidth() == 2
                    and wav.getframerate() == SAMPLE_RATE and wav.getnframes() > 0
                    and len(wav.readframes(wav.getnframes())) == wav.getnframes() * 2)
    except (OSError, EOFError, wave.Error):
        return False


def synthesize_chunk(provider: str, cfg: dict, text: str, raw: Path) -> Path:
    for attempt in range(1, 4):
        try:
            return cloud_tts.synthesize_with_config(provider, cfg, text, raw)
        except cloud_tts.CloudTTSError as exc:
            # 不记录服务返回的正文，防止上游错误响应回显凭据或参考音频。
            if attempt == 3:
                raise RuntimeError(f"{provider} 连续 3 次失败（{type(exc).__name__}）；段缓存已保留") from None
            print(f"[!] {provider} 第 {attempt} 次失败，重试", flush=True)
            time.sleep(attempt * 2)
    raise AssertionError("unreachable")


def render(plan: dict, configs: dict, output: Path) -> dict:
    """逐段落盘；全部解码成功后才发布成品。失败保留缓存，换声音会换缓存。"""
    signature = digest(plan)
    sidecar = output.with_suffix(".json")
    if output.exists():
        if sidecar.is_file():
            old = json.loads(sidecar.read_text(encoding="utf-8"))
            if old.get("plan_sha256") == signature and old.get("audio_sha256") == file_hash(output):
                print("[✓] 同稿同音色成品已存在，零合成调用复用", flush=True)
                return old
        raise ValueError("输出已存在但与本次输入不一致；请另选输出文件名")
    for provider in {cfg[0] for cfg in configs.values()}:
        if not cloud_tts.has_provider_secret(provider):
            raise ValueError(f"{provider} 未配置 Keychain 凭据")
    work = output.parent / f".dialogue-segments-{signature[:20]}"
    work.mkdir(parents=True, exist_ok=True)
    silence = work / "gap.wav"
    with wave.open(str(silence), "wb") as wav:
        wav.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
        wav.writeframes(b"\0\0" * round(SAMPLE_RATE * plan["gap_ms"] / 1000))
    sequence, timeline = [], []
    cursor, calls, hits = 0.0, 0, 0
    previous = None
    for i, chunk in enumerate(plan["chunks"], 1):
        role = chunk["speaker"]
        target = work / f"{i:04d}-{role}.wav"
        was_cached = cached_wav_valid(target)
        if was_cached:
            hits += 1
        else:
            provider, cfg = configs[role]
            raw = synthesize_chunk(provider, cfg, chunk["text"], work / f"{i:04d}.raw.wav")
            calls += 1
            temporary = work / f"{i:04d}.normalizing.wav"
            run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", NORMALIZE,
                 "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(temporary)])
            if not cached_wav_valid(temporary):
                raise RuntimeError(f"第 {i} 段没有有效音频，缓存保留供排查")
            temporary.replace(target)
        if previous is not None and role != previous and plan["gap_ms"]:
            sequence.append(silence)
            cursor += plan["gap_ms"] / 1000
        duration = ffprobe_duration(target)
        timeline.append({**chunk, "start_seconds": round(cursor, 3),
                         "duration_seconds": round(duration, 3)})
        cursor += duration
        sequence.append(target)
        previous = role
        print(f"[{i}/{len(plan['chunks'])}] {role} · {duration:.1f}s"
              f" · {'缓存' if was_cached else '新合成'}", flush=True)
    # 双引号不参与 shell；单引号按 ffconcat 文件格式转义。
    listing = work / "concat.txt"
    listing.write_text("".join("file '" + str(p.resolve()).replace("'", "'\\''") + "'\n"
                               for p in sequence), encoding="utf-8")
    staged = work / "ready.m4a"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-af", ALIMITER, "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "aac", "-b:a", "96k",
         "-metadata", "comment=AI 合成双人试播；克隆音色不代表原声本人观点", str(staged)])
    run(["ffmpeg", "-v", "error", "-i", str(staged), "-f", "null", "-"])
    report = {"plan_sha256": signature, "audio_sha256": file_hash(staged),
              "duration_seconds": ffprobe_duration(staged), "ai_generated": True,
              "preview": plan["preview"], "speakers": plan["speakers"],
              "decode_ok": True, "synthesis_calls": calls, "cache_hits": hits,
              "timeline": timeline}
    staged.replace(output)
    sidecar.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", default=ROOT / "config/dialogue.json", type=Path)
    parser.add_argument("--limit", default=0, type=int, help="只合前 N 个发言轮次，标为试听")
    parser.add_argument("--dry-run", action="store_true", help="校验和查看计划，不读 Key、不调用合成")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.suffix.lower() != ".m4a":
        raise ValueError("输出扩展名须为 .m4a")
    plan, configs = build_plan(args.input.read_text(encoding="utf-8"),
                               json.loads(args.config.read_text(encoding="utf-8")), args.limit)
    print(f"[*] {plan['selected_turns']}/{plan['total_turns']} 轮 · {len(plan['chunks'])} 段"
          f" · 指纹 {digest(plan)[:20]}", flush=True)
    if args.dry_run:
        return 0
    if not all(shutil.which(name) for name in ("ffmpeg", "ffprobe")):
        raise ValueError("需要已有的 ffmpeg 和 ffprobe")
    report = render(plan, configs, output)
    print(f"[✓] {output} · 实测 {report['duration_seconds']:.1f}s · 完整解码成功", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("[!] 已中断，段缓存保留，同命令可续跑", file=sys.stderr)
        sys.exit(130)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"[✗] {exc}", file=sys.stderr)
        sys.exit(1)
