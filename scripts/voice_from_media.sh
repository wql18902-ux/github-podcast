#!/bin/bash
# 任意音视频 → 一套可用的克隆音色（wav + txt）
# 用法: voice_from_media.sh <输入> <音色名> [start] [dur]
set -euo pipefail
IN="${1:?用法: voice_from_media.sh <输入> <音色名> [start] [dur]}"
NAME="${2:?缺音色名}"
SS="${3:-0}"; DUR="${4:-18}"
ROOT=~/ai-brain/github-podcast
SV=~/ai-brain/转录系统/sensevoice-onnx
PY=/opt/homebrew/bin/python3
URL=http://127.0.0.1:18923

bash "$ROOT/scripts/make_voice_ref.sh" "$IN" "$NAME" "$SS" "$DUR"

# 起 SenseVoice（记得 env -u PYTHONPATH + homebrew python；服务是常驻的，已在跑就复用）
STARTED=0
if ! curl -sf -m 3 "$URL/v1/audio/models/status" >/dev/null 2>&1; then
  (cd "$SV" && nohup env -u PYTHONPATH "$PY" scripts/sensevoice_onnx_server.py --port 18923 \
     > /tmp/sensevoice-server.log 2>&1 & disown)
  STARTED=1
  for i in $(seq 1 30); do
    sleep 2
    curl -sf -m 3 "$URL/v1/audio/models/status" >/dev/null 2>&1 && break
  done
fi
curl -sf -m 3 "$URL/v1/audio/models/status" >/dev/null 2>&1 || {
  echo "[✗] SenseVoice 服务没起来，日志见 /tmp/sensevoice-server.log"; exit 1; }

env -u PYTHONPATH "$PY" "$SV/scripts/transcribe.py" \
  "$ROOT/voices/$NAME.wav" -o "$ROOT/voices/$NAME.txt.raw"
# SenseVoice 输出无标点 → 去标题行、补句读落 .txt
tail -n +3 "$ROOT/voices/$NAME.txt.raw" | tr -d '\n' > "$ROOT/voices/$NAME.txt"
rm -f "$ROOT/voices/$NAME.txt.raw"
# 本次自己起的服务，用完收掉（别让常驻进程挂着占内存，也避免背景进程吊住终端）
if [ "$STARTED" = "1" ]; then
  pkill -f sensevoice_onnx_server && echo "[*] 已停止本次启动的 SenseVoice 服务"
fi
echo "[✓] 音色就绪: $ROOT/voices/$NAME.wav + .txt"
echo "    启用：cp voices/$NAME.wav voices/podcast-voice.wav && cp voices/$NAME.txt voices/podcast-voice.txt"
