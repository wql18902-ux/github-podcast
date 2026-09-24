#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${1:-8787}"
HOST="${TTS_CONSOLE_HOST:-127.0.0.1}"
SDK_PYTHON="$HOME/.local/share/ai-jarvis/tts-console/venv/bin/python"

if [ -x "$SDK_PYTHON" ]; then
  exec "$SDK_PYTHON" scripts/tts_console.py --host "$HOST" --port "$PORT"
fi

exec /opt/homebrew/bin/python3 scripts/tts_console.py --host "$HOST" --port "$PORT"
