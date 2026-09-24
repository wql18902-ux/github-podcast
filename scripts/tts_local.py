#!/usr/bin/env python3
"""本地 TTS：VoxCPM2 (2B, GGUF Q8 + Metal) 整期合成。

用法:
  python3 scripts/tts_local.py --input output/latest-script.md --output /tmp/ep.m4a
  python3 scripts/tts_local.py --input script.md --output out.m4a --limit 2

流程: 剥 markdown → 按句分段(≤120字) → 自动拉起 llama-tts-server →
POST /v1/audio/speech 逐段出 wav → ffmpeg 拼接 → m4a。

语速: **原速**（生成多少秒就多少秒），不做 148 汉字/分定标——那是豆包
seed-audio 的档位。`--pace` 留作可选，不传即原速；除非用户明确要求，别传。

音色（2026-09-11 修）: 不传参考音频时，服务端走无条件的 rt->generate，
**每段现采一个新音色**（seed 只锁「同文本两次一致」）→ 整期音色乱跳。
所以正常整期必须走克隆模式：传 `--voice-ref <wav>`（或放好
`voices/podcast-voice.wav`，脚本自动启用）。可选 `--voice-ref-text`/同名 .txt
提升克隆稳定性。换音色 = 换那个 wav 文件。

模型/引擎路径默认指向 ai-brain/research/本地TTS调研/research-2026-09-10/tools/，
可用环境变量覆盖: TTS_LOCAL_BIN / TTS_LOCAL_BASE_LM / TTS_LOCAL_ACOUSTIC /
TTS_LOCAL_PORT / TTS_LOCAL_VOICE_REF。
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

# VoxCPM2 引擎目录：模型文件 + llama-tts-server 二进制都在这里。
# 用环境变量 VOXCPM_TOOLS_DIR 指过去；默认取 ~/research/local-tts/tools（见 README「本地 TTS」一节）。
TOOLS = Path(os.environ.get("VOXCPM_TOOLS_DIR", str(Path.home() / "research" / "local-tts" / "tools")))
DEFAULT_BIN = TOOLS / "llama-cpp-omni-git/build/bin/llama-tts-server"
DEFAULT_BASE_LM = TOOLS / "voxcpm2-gguf/VoxCPM2-BaseLM-Q8_0.gguf"
DEFAULT_ACOUSTIC = TOOLS / "voxcpm2-gguf/VoxCPM2-Acoustic-F16.gguf"
DEFAULT_PORT = int(os.environ.get("TTS_LOCAL_PORT", "8083"))
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# 播客标准音色：存在即自动启用克隆模式（全期锁一个音色）。
# 换音色 = 换这个文件；清空（删掉）= 回到每段随机音色。
DEFAULT_VOICE_REF = PROJECT_ROOT / "voices" / "podcast-voice.wav"
HAN = re.compile(r"[\u4e00-\u9fff]")
VOICE_SEED = 42  # 仅在「无参考音频」时生效（那种模式下每段音色随机，见下）

SPOKEN_EXACT = {
    "CLI": "命令行工具",
    "YOLO": "一路放行",
    "npm": "N P M",
    "README": "说明文档",
    ".toml": "TOML",
    ".env": "环境变量文件",
    "GEMINI.md": "Gemini 的项目规则文件",
    "AGENTS.md": "AGENTS 规则文件",
    "TOOL_CONFIRMATION_REQUEST": "工具确认请求事件",
    "TOOLS_REQUIRING_NARROWING": "需要缩小范围的工具集合",
    "allowRedirection": "允许重定向标记",
    "confirmed: false": "确认结果是否",
    "requiresUserConfirmation: true": "要求用户确认为真",
    "claude -p": "Claude 命令行模式",
    "Apache-2.0": "Apache 二点零许可证",
    "__proto__": "双下划线 proto 双下划线",
    "Abort trap: 6": "Abort trap 六号错误",
}

EXT_NAMES = {
    "py": "Python",
    "ts": "TypeScript",
    "tsx": "TypeScript",
    "js": "JavaScript",
    "json": "JSON",
    "toml": "TOML",
    "md": "Markdown",
    "sh": "Shell",
    "rs": "Rust",
    "go": "Go",
    "sql": "SQL",
}


def _spoken_code(token):
    """把会被 TTS 逐字符念坏的代码标记改成可听的短句。"""
    s = token.strip().strip("`")
    if not s:
        return ""
    if s in SPOKEN_EXACT:
        return SPOKEN_EXACT[s]

    s = s.lstrip("~/")
    if s.startswith("@"):
        return re.sub(r"[-_/]+", " ", s).strip()

    # 路径优先按「目录 + 文件类型」处理，避免模型念出一串斜杠和点号。
    if "/" in s:
        parts = [p for p in s.split("/") if p and p not in (".", "~")]
        if parts and "." in parts[-1] and not parts[-1].startswith("."):
            filename = parts[-1]
            stem, ext = filename.rsplit(".", 1)
            stem = re.sub(r"[-_]+", " ", stem).strip()
            kind = EXT_NAMES.get(ext.lower())
            if len(parts) > 1:
                parent = " ".join(
                    re.sub(r"[-_]+", " ", p).lstrip(".").strip() for p in parts[:-1]
                )
                if kind:
                    return f"{parent} 目录下的 {stem} 这个 {kind} 文件"
                return f"{parent} 目录下的 {filename} 文件"
            if kind:
                return f"{stem} 这个 {kind} 文件"
            return f"{stem} 文件"
        parent = " ".join(re.sub(r"[-_]+", " ", p).lstrip(".").strip() for p in parts)
        return f"{parent} 目录"

    ext_match = re.fullmatch(r"\.([A-Za-z0-9]+)", s)
    if ext_match:
        kind = EXT_NAMES.get(ext_match.group(1).lower())
        return f"{kind} 文件" if kind else s

    file_match = re.fullmatch(r"(.+)\.([A-Za-z0-9]+)", s)
    if file_match:
        stem, ext = file_match.groups()
        kind = EXT_NAMES.get(ext.lower())
        if kind:
            stem = re.sub(r"[-_]+", " ", stem).strip()
            return f"{stem} 的 {kind} 文件"
        return s

    s = re.sub(r"[_\-]+", " ", s)
    s = s.replace(":", "：")
    return s


def _replace_spoken_terms(text):
    text = re.sub(r"\bGemini CLI\b", "杰米尼 命令行工具", text, flags=re.I)
    text = re.sub(r"\bGemini\b", "杰米尼", text, flags=re.I)
    text = re.sub(r"\bGoogle\b", "谷歌", text, flags=re.I)
    text = text.replace("Apache-2.0", "阿帕奇 二点零许可证")
    text = re.sub(r"\bApache\b", "阿帕奇", text, flags=re.I)
    text = re.sub(r"\b([A-Za-z][A-Za-z0-9.-]*) CLI\b", r"\1 命令行工具", text)
    text = re.sub(r"\bYOLO\b", "一路放行", text, flags=re.I)
    text = re.sub(r"\bnpm\b", "N P M", text, flags=re.I)
    text = re.sub(r"\bREADME\b", "说明文档", text, flags=re.I)
    text = re.sub(r"\bheadless\b", "无界面", text, flags=re.I)
    text = re.sub(r"\bdiff\b", "对比", text)
    text = re.sub(r"\bhook\b", "钩子", text)
    text = re.sub(r"\bcheckpoint\b", "检查点", text)
    text = re.sub(r"\bUI\b", "界面", text)
    text = re.sub(r"\bIT\b", "信息技术", text)
    text = re.sub(r"\bMCP\b", "M C P", text)
    text = text.replace(" > ", " 大于号 ")
    text = text.replace("文件 里", "文件里")
    text = text.replace("目录 下", "目录下")
    return text


def _table_to_speech(rows):
    """Markdown 表格转成一句句可听的话，不让 TTS 念竖线和横线。"""
    if not rows:
        return ""
    parsed = [[c.strip() for c in row.strip().strip("|").split("|")] for row in rows]
    headers = parsed[0]
    out = []
    for row in parsed[1:]:
        if row and all(re.fullmatch(r":?-{3,}:?", c or "") for c in row):
            continue
        pairs = []
        for i, value in enumerate(row[1:], 1):
            if not value:
                continue
            header = headers[i] if i < len(headers) else f"第 {i + 1} 列"
            header = re.sub(r"（[^）]*）", "", header).strip()
            header = _replace_spoken_terms(
                re.sub(r"`([^`]+)`", lambda m: _spoken_code(m.group(1)), header)
            ).replace("`", "")
            value = _replace_spoken_terms(
                re.sub(r"`([^`]+)`", lambda m: _spoken_code(m.group(1)), value)
            ).replace("`", "")
            pairs.append(f"{header}是{value}")
        if pairs:
            lead = row[0].strip() if row else ""
            lead = _replace_spoken_terms(
                re.sub(r"`([^`]+)`", lambda m: _spoken_code(m.group(1)), lead)
            ).replace("`", "")
            out.append((lead + "：" if lead else "") + "；".join(pairs) + "。")
    return "\n".join(out)


def wav_duration(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def probe_duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        text=True,
    ).strip()
    return float(out)


def strip_markdown(text):
    lines = []
    source = text.splitlines()
    i = 0
    while i < len(source):
        line = source[i]
        s = line.strip()
        if s.startswith("|"):
            table = []
            while i < len(source) and source[i].strip().startswith("|"):
                table.append(source[i].strip())
                i += 1
            spoken = _table_to_speech(table)
            if spoken:
                lines.append(spoken)
            continue
        i += 1
        if not s or s.startswith("#") or s.startswith(">") or s == "---" or s == "（完）":
            continue
        # 调研稿元信息行（信息截止：YYYY-MM-DD），不念进音频
        if s.startswith("信息截止"):
            continue
        s = re.sub(r"`([^`]+)`", lambda m: _spoken_code(m.group(1)), s)
        s = s.replace("`", "")
        lines.append(s)
    body = "\n".join(lines)
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)
    body = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", body)
    body = body.replace("**", "").replace("*", "")
    return _replace_spoken_terms(body).strip()


def split_sentences(text, max_len=120):
    raw = re.split(r"(?<=[。！？；])", text)
    raw = [s.strip().replace("\n", "") for s in raw if s.strip()]
    segments, buf = [], ""
    for s in raw:
        if len(buf) + len(s) <= max_len:
            buf += s
        else:
            if buf:
                segments.append(buf)
            while len(s) > max_len:
                cut = s.rfind("，", 0, max_len)
                cut = cut if cut > 20 else max_len
                segments.append(s[:cut])
                s = s[cut:]
            buf = s
    if buf:
        segments.append(buf)
    return segments


def server_health(url):
    try:
        with urllib.request.urlopen(url + "/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def post_speech(url, text, timeout=900, retries=3, ref_b64=None, ref_text=""):
    payload = {"model": "voxcpm2", "input": text,
               "response_format": "wav", "seed": VOICE_SEED}
    if ref_b64:
        payload["reference_audio"] = ref_b64
        if ref_text:
            payload["reference_text"] = ref_text
    req = urllib.request.Request(
        url + "/v1/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"[!] 第 {i + 1} 次请求失败: {e}", file=sys.stderr)
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"合成请求失败 {retries} 次: {last}")


def start_server(bin_path, base_lm, acoustic, port, log_file):
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = log_file.open("w")
    proc = subprocess.Popen(
        [
            str(bin_path),
            "--voxcpm2-base-lm", str(base_lm),
            "--voxcpm2-acoustic", str(acoustic),
            "--host", "127.0.0.1",
            "--port", str(port),
        ],
        stdout=fh,
        stderr=subprocess.STDOUT,
    )
    return proc


def wait_server(url, proc, timeout=240):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-tts-server 退出码 {proc.returncode}，日志见末尾")
        if server_health(url):
            return
        time.sleep(2)
    raise RuntimeError("llama-tts-server 启动超时")


def atempo_chain(factor):
    """factor = 目标时长/实际时长 时: <1 慢放, >1 快放; 拆多段支持 <0.5。"""
    filters = []
    while factor < 0.5:
        filters.append("atempo=0.7")
        factor /= 0.7
    if factor > 100:
        raise ValueError(f"factor {factor:.3f} 超过 ffmpeg atempo 上限 100")
    filters.append(f"atempo={factor:.4f}")
    return ",".join(filters)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--pace", type=float, default=0.0,
                    help="0=原速（默认，生成多少秒就多少秒）；>0 时按目标汉字/分钟定标")
    ap.add_argument("--max-chars", type=int, default=120)
    ap.add_argument("--limit", type=int, default=0, help="只合成前 N 段（测试）")
    ap.add_argument("--voice-ref", type=Path,
                    default=(Path(os.environ["TTS_LOCAL_VOICE_REF"])
                             if os.environ.get("TTS_LOCAL_VOICE_REF") else None),
                    help="参考音频 WAV：给了=克隆模式（全期锁定同一音色）；"
                         "不给=每段随机音色（VoxCPM2 默认行为）")
    ap.add_argument("--voice-ref-text", default="",
                    help="参考音频对应的文本（可选，提升克隆稳定性）")
    ap.add_argument("--denoise", choices=["off", "deesser", "deesser-treble"],
                    default=os.environ.get("TTS_LOCAL_DENOISE", "off"),
                    help="句尾爆音抑制（VoxCPM2 声码器在句末的'滋'声）："
                         "off=不处理（默认）；deesser=齿音抑制轻档（路线一）；"
                         "deesser-treble=再叠 8k 高架轻削（路线二）")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--server-bin", type=Path,
                    default=Path(os.environ.get("TTS_LOCAL_BIN", DEFAULT_BIN)))
    ap.add_argument("--base-lm", type=Path,
                    default=Path(os.environ.get("TTS_LOCAL_BASE_LM", DEFAULT_BASE_LM)))
    ap.add_argument("--acoustic", type=Path,
                    default=Path(os.environ.get("TTS_LOCAL_ACOUSTIC", DEFAULT_ACOUSTIC)))
    ap.add_argument("--keep-server", action="store_true")
    args = ap.parse_args()

    if not args.input.exists():
        raise SystemExit(f"[✗] 输入不存在: {args.input}")
    if shutil.which("ffmpeg") is None:
        raise SystemExit("[✗] 找不到 ffmpeg")
    if not args.server_bin.exists():
        raise SystemExit(f"[✗] llama-tts-server 不存在: {args.server_bin}")

    if args.voice_ref is None and DEFAULT_VOICE_REF.exists():
        args.voice_ref = DEFAULT_VOICE_REF
    ref_text = args.voice_ref_text
    if not ref_text and args.voice_ref is not None:
        _txt = args.voice_ref.with_suffix(".txt")
        if _txt.exists():
            ref_text = _txt.read_text(encoding="utf-8").strip()
    ref_b64 = None
    if args.voice_ref is not None:
        if not args.voice_ref.exists():
            raise SystemExit(f"[✗] 参考音频不存在: {args.voice_ref}")
        ref_b64 = base64.b64encode(args.voice_ref.read_bytes()).decode("ascii")

    text = strip_markdown(args.input.read_text(encoding="utf-8"))
    if not text:
        raise SystemExit("[✗] 剥完 markdown 后没有正文")
    segments = split_sentences(text, args.max_chars)
    if args.limit:
        segments = segments[: args.limit]
    han_total = len(HAN.findall("".join(segments)))
    pace_txt = f"目标 {args.pace:.0f} 字/分" if args.pace > 0 else "原速"
    voice_txt = (f"克隆锁音色({args.voice_ref.name})" if ref_b64
                 else "每段随机音色(未给 --voice-ref)")
    print(f"[*] {len(segments)} 段 / 汉字 {han_total} / {pace_txt} / {voice_txt}")

    url = f"http://127.0.0.1:{args.port}"
    started_here = False
    proc = None
    log_file = Path(tempfile.gettempdir()) / "tts_local_server.log"
    if not server_health(url):
        print("[*] 启动 llama-tts-server ...")
        proc = start_server(args.server_bin, args.base_lm, args.acoustic, args.port, log_file)
        started_here = True
        wait_server(url, proc)
        print("[✓] server 就绪")
    else:
        print("[✓] 复用已运行的 server")

    tmp = Path(tempfile.mkdtemp(prefix="tts_local_"))
    try:
        wavs = []
        for i, seg in enumerate(segments, 1):
            data = post_speech(url, seg, ref_b64=ref_b64, ref_text=ref_text)
            f = tmp / f"seg{i:03d}.wav"
            f.write_bytes(data)
            wavs.append(f)
            print(f"[{i}/{len(segments)}] {len(seg)} 字 -> {wav_duration(f):.1f}s")

        list_file = tmp / "list.txt"
        list_file.write_text("".join(f"file '{f}'\n" for f in wavs), encoding="utf-8")
        full = tmp / "full.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(list_file), "-c", "copy", str(full)],
            check=True,
        )
        actual = wav_duration(full)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        filters = []
        if args.pace > 0:
            target = han_total / (args.pace / 60.0)
            factor = actual / target
            filters.append(atempo_chain(factor))
        # 模型输出的峰值可以顶到 0 dBFS（实测：老的非克隆产物解码后 Peak +2.4 dB），
        # 始终挂限幅到 -1.5 dBTP（0.8414 = 10^(-1.5/20)）；level=disabled = 只削峰、不动整体响度。
        filters.append("alimiter=limit=0.8414:level=disabled")
        # 句尾爆音抑制（2026-09-12 实测）：VoxCPM2 声码器在句末能量骤降处产生约
        # 140ms 的宽频爆音（峰值可顶到 -0.8 dB，高频比正常句尾高 25 dB），稳态
        # 降噪（afftdn/anlmdn）无效，deesser 对症。
        #   路线一 deesser 轻档：爆音 -0.8 -> -15.9 dB，正常语音几乎不动（实测 -0.3 dB）
        #   路线二 再叠 8k 高架：爆音再降 ~1.3 dB，代价高频细节略少
        # 放在限幅之前：先把爆音压下去，再削峰兜底。
        if args.denoise == "deesser":
            filters.insert(-1, "deesser=i=0.4:m=0.5:f=0.5")
        elif args.denoise == "deesser-treble":
            filters.insert(-1, "deesser=i=0.4:m=0.5:f=0.5")
            filters.insert(-1, "treble=g=-4:f=8000:width_type=q:w=0.7")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(full),
               "-ar", "48000", "-ac", "1", "-b:a", "64k",
               "-filter:a", ",".join(filters), str(args.output)]
        subprocess.run(cmd, check=True)
        final_sec = probe_duration(args.output)
        print(f"[✓] 完成: {args.output}")
        pace_txt = (f"原生 {actual:.0f}s（未变速）" if args.pace <= 0
                    else f"原生 {actual:.0f}s → 定标 {final_sec:.0f}s")
        print(f"    {pace_txt}，{han_total / final_sec * 60:.0f} 汉字/分，"
              f"1.5x 听 = {han_total / final_sec * 90:.0f} 汉字/分")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if started_here and not args.keep_server and proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            print("[*] 已停止本次启动的 server")


if __name__ == "__main__":
    main()
