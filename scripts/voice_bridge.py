#!/usr/bin/env python3
"""本机语音桥接 —— 让网页能用你本机的 TTS key，而不必把 key 放到任何服务器上。

公开站上一段音频都没有，也一个 key 都不存。要做「上传音色 → 生成语音」，
就在自己机器上跑这个：

    python3 scripts/voice_bridge.py

它只监听 127.0.0.1:8794，只接受本机 localhost 页面跨域，每天最多合成 5 次（额度存在本机）。
有参考音走克隆（mimo-v2.5-tts-voiceclone），没有就按音色描述走设计（-voicedesign）。

接口：
    GET  /health  → {"ok": true, "quota": {"used": 1, "limit": 5, "left": 4}}
    POST /tts     → {"audio": "<base64 wav>", "seconds": 12.3, "quota": {...}}

Key 从 macOS Keychain 读（service ai-jarvis-tts-console / account mimo_api），
本文件不碰任何密钥，也不往日志里写。
"""

from __future__ import annotations

import base64
import os
import subprocess
import threading
import datetime as dt
import hashlib
import json
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import cloud_tts  # noqa: E402

PORT = int(os.environ.get("SOURCECAST_BRIDGE_PORT", "8794"))
TTS_LOCK = threading.Lock()
DAILY_LIMIT = 5
MAX_BODY = 12 * 1024 * 1024
UPLOAD_DIR = PROJECT_ROOT / "output" / "tts-console" / "_bridge"
QUOTA_FILE = Path.home() / ".config" / "ai-jarvis" / "tts-console" / "bridge-quota.json"

ALLOWED = {
    "http://127.0.0.1:8793",
    "http://localhost:8793",
    "http://127.0.0.1:8791",
    "http://localhost:8791",
}


def quota_state() -> dict:
    today = dt.date.today().isoformat()
    try:
        data = json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if data.get("date") != today:
        data = {"date": today, "used": 0}
    data.setdefault("used", 0)
    return data


def quota_bump() -> dict:
    data = quota_state()
    data["used"] += 1
    QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUOTA_FILE.write_text(json.dumps(data), encoding="utf-8")
    return data


def quota_public(data: dict) -> dict:
    used = int(data.get("used", 0))
    return {"used": used, "limit": DAILY_LIMIT, "left": max(0, DAILY_LIMIT - used)}


class Handler(BaseHTTPRequestHandler):
    server_version = "SourcecastBridge/1.0"

    def log_message(self, fmt, *args):  # 静默：不把请求细节写进终端
        pass

    # ── CORS ───────────────────────────────────────
    def _cors(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin in ALLOWED

    # ── 路由 ───────────────────────────────────────
    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):  # noqa: N802
        if not self._origin_ok():
            self._json(403, {"error": "这个来源不被允许"})
            return
        if self.path.split("?")[0] == "/health":
            self._json(200, {"ok": True, "quota": quota_public(quota_state()), "localAvailable": bool(os.environ.get("SOURCECAST_LOCAL_TTS_TOOLS"))})
            return
        self._json(404, {"error": "只有 /health 和 /tts"})

    def do_POST(self):  # noqa: N802
        if not TTS_LOCK.acquire(blocking=False):
            self._json(409, {"error":"已有语音正在生成，请等本次完成"})
            return
        try:
            self._post_tts()
        finally:
            TTS_LOCK.release()

    def _post_tts(self):
        if not self._origin_ok():
            self._json(403, {"error": "这个来源不被允许"})
            return
        if self.path.split("?")[0] != "/tts":
            self._json(404, {"error": "只有 /health 和 /tts"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._json(413, {"error": "请求体太大或为空"})
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._json(400, {"error": "不是合法 JSON"})
            return

        text = (payload.get("text") or "").strip()
        if not text:
            self._json(400, {"error": "没有要念的文本"})
            return
        if len(text) > 400:
            self._json(400, {"error": "一次最多 400 字，长稿请分批"})
            return

        state = quota_state()
        if state["used"] >= DAILY_LIMIT:
            self._json(429, {"error": f"今天的 {DAILY_LIMIT} 次用完了", "quota": quota_public(state)})
            return

        ref = payload.get("ref")
        style = (payload.get("style") or "").strip()
        try:
            if ref:
                wav_bytes = self._decode_ref(ref)
                UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                name = hashlib.sha1(wav_bytes).hexdigest()[:12] + ".wav"
                ref_path = UPLOAD_DIR / name
                ref_path.write_bytes(wav_bytes)
                provider = "mimo_tts_clone"
                cfg = cloud_tts.get_provider_config(provider)
                cfg.setdefault("extra", {})["reference_audio_path"] = str(ref_path)
                cfg["extra"]["style_prompt"] = style
            else:
                provider = "mimo_tts" if payload.get("mode") == "preset" else "mimo_tts_design"
                cfg = cloud_tts.get_provider_config(provider)
                cfg.setdefault("extra", {})["style_prompt"] = (
                    style.split("·")[0].strip() or "沉稳温和的中文男声，语速适中"
                )

            out = UPLOAD_DIR / f"out-{hashlib.sha1(text.encode()).hexdigest()[:10]}.wav"
            if payload.get("engine") == "local":
                if not ref:
                    raise ValueError("本地克隆需要上传参考音")
                with tempfile.NamedTemporaryFile(mode="w",suffix=".txt",encoding="utf-8") as source:
                    source.write(text);source.flush()
                    local_env = os.environ.copy()
                    if os.environ.get("SOURCECAST_LOCAL_TTS_TOOLS"):
                        local_env["SOURCECAST_LOCAL_TTS_TOOLS"]=os.environ["SOURCECAST_LOCAL_TTS_TOOLS"]
                    result = subprocess.run([sys.executable,str(PROJECT_ROOT/"scripts"/"tts_local.py"),"--input",source.name,"--output",str(out),"--voice-ref",str(ref_path),"--voice-ref-text","","--denoise","deesser","--port","8085"],capture_output=True,text=True,timeout=240,env=local_env)
                    if result.returncode:
                        raise ValueError("本地引擎未完成合成，请检查 VoxCPM2 模型与 ffmpeg 配置")
            else:
                cloud_tts.synthesize_with_config(provider, cfg, text, out)
            audio = out.read_bytes()
            out.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"[:300]})
            return

        state = quota_bump()
        seconds = self._wav_seconds(audio)
        self._json(200, {
            "audio": base64.b64encode(audio).decode("ascii"),
            "seconds": round(seconds, 2),
            "mode": "local" if payload.get("engine") == "local" else "clone" if ref else "design",
            "quota": quota_public(state),
        })

    # ── 小工具 ─────────────────────────────────────
    @staticmethod
    def _decode_ref(ref: str) -> bytes:
        if not ref.startswith("data:"):
            raise ValueError("参考音要传 data URL")
        _, b64 = ref.split(",", 1)
        raw = base64.b64decode(b64)
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError("参考音太大")
        if raw[:4] != b"RIFF":
            raise ValueError("参考音需要是 wav（浏览器里裁一段导出即可）")
        return raw

    @staticmethod
    def _wav_seconds(data: bytes) -> float:
        import wave

        with tempfile.NamedTemporaryFile(suffix=".wav") as fh:
            fh.write(data)
            fh.flush()
            with wave.open(fh.name) as w:
                return w.getnframes() / float(w.getframerate())


def main() -> int:
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"页声 · 本机语音桥接已起在 http://127.0.0.1:{PORT}")
    print(f"额度：每天 {DAILY_LIMIT} 次，存在 {QUOTA_FILE}")
    print("回到网页里点「检测」。Ctrl-C 结束。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
