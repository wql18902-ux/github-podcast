#!/bin/bash
# 播客本地合成兜底 —— 定时任务专用（可挂 Trae / Hermes / launchd，纯脚本 0 token）
#
# 干什么：检查夜班稿子 OK + 今天还没有成品音频 → 用本地 VoxCPM2 顶一版
# 产物：output/audio/<日期>-ep-local-fallback.m4a（带 -local，跟豆包那条不撞名）
# 过程写 output/local-fallback.log
#
# 降噪档位（2026-09-12 新增，治 VoxCPM2 句尾"滋"声）：
#   DENOISE=off             不处理（旧行为）
#   DENOISE=deesser         方案一：齿音抑制轻档（推荐，爆音 -0.8 → -15.9 dB）
#   DENOISE=deesser-treble  方案二：再叠 8k 高架轻削（爆音再降 ~1.3 dB）
# 默认值在下面 DENOISE="${DENOISE:-deesser}" 一行改。
#
# 用法：
#   bash scripts/local-fallback.sh                    # 默认档位
#   DENOISE=deesser-treble bash scripts/local-fallback.sh
#   DENOISE=off bash scripts/local-fallback.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 0

# ncm-cli / lark-cli 在 ~/.npm-global/bin，默认 cron PATH 里没有；homebrew python/ffmpeg 同理
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.npm-global/bin:$PATH"

# ── 默认降噪档位 ─────────────────────────────────────────────
# 想换默认档位，只改这一行的 deesser 即可（off / deesser / deesser-treble）
DENOISE="${DENOISE:-deesser}"

TODAY=$(date +%F)
LOG=output/local-fallback.log
echo "===== $(date '+%F %T') 兜底检查 (denoise=$DENOISE) =====" >> "$LOG"

# 1. 状态闸：夜班没成功就不合成（跟豆包读同一道闸）
if ! head -1 output/latest-status.txt 2>/dev/null | grep -q '^OK'; then
    echo "[skip] status not OK" >> "$LOG"
    exit 0
fi

# 2. 今天已经有成品（豆包或本地）就跳过
if ls output/audio/${TODAY}*.m4a output/audio/${TODAY}*.mp3 >/dev/null 2>&1; then
    echo "[skip] $TODAY 已有成品音频" >> "$LOG"
    exit 0
fi

# 3. 稿件得在
if [ ! -f output/latest-script.md ]; then
    echo "[skip] no script" >> "$LOG"
    exit 0
fi

# 4. 已经有合成在跑就别叠加（16G 机器跑不动两个）
if pgrep -f "tts_local.py" >/dev/null 2>&1; then
    echo "[skip] 已有 tts_local.py 在跑" >> "$LOG"
    exit 0
fi

# 5. 真跑：原速、克隆音色（tts_local.py 自动认 voices/podcast-voice.wav）
echo "[run] 本地兜底合成 ${TODAY}（denoise=${DENOISE}）" >> "$LOG"
env -u PYTHONPATH python3 scripts/tts_local.py \
    --input output/latest-script.md \
    --output "output/audio/${TODAY}-ep-local-fallback.m4a" \
    --denoise "$DENOISE" >> "$LOG" 2>&1
echo "[done] exit=$?" >> "$LOG"
