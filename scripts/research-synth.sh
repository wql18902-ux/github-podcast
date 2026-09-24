#!/bin/bash
# 调研稿 → 播客音频（Trae 定时任务用，2026-09-12 立）
#
# 干什么：
#   1. 取 output/research/ 下修改时间最新的 .md
#   2. 今天已合成过（output/audio/<日期>-research* 存在）就跳过
#   3. 没有别的 tts_local.py 在跑（16G 机器同时只能跑一个）才动手
#   4. 合成 output/audio/<日期>-research-<主题>.m4a
#
# 红线：只读稿件、只写 output/audio/；不 kill 任何进程；pipeline.sh 报错就原样退出，不改脚本。
#
# 用法：
#   bash scripts/research-synth.sh
#   DENOISE=deesser-treble bash scripts/research-synth.sh    # 换降噪档（默认 deesser）
set -uo pipefail
cd "$(dirname "$0")/.." || exit 0
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.npm-global/bin:$PATH"

# 降噪档位：兜底默认 deesser（方案一，2026-09-12 用户拍板）
DENOISE="${DENOISE:-deesser}"
TODAY=$(date +%F)
RESEARCH_DIR=output/research
LOG=output/research-synth.log
STATE=output/research-synth-last.tsv
FORCE="${FORCE:-0}"

{
echo "===== $(date '+%F %T') 调研稿合成检查 (denoise=$DENOISE) ====="

# 1. 稿件目录得在
if [ ! -d "$RESEARCH_DIR" ]; then
    echo "[skip] 无稿目录 $RESEARCH_DIR"
    echo "无新稿，跳过"
    exit 0
fi

# 2. 取最新 .md
SCRIPT=$(ls -t "$RESEARCH_DIR"/*.md 2>/dev/null | head -1)
if [ -z "$SCRIPT" ]; then
    echo "[skip] output/research/ 下没有 .md"
    echo "无新稿，跳过"
    exit 0
fi
echo "[info] 最新稿件：$SCRIPT"
SOURCE_HASH=$(shasum -a 256 "$SCRIPT" | awk '{print $1}')
# 稿件内容或 TTS 预处理任一变化，都算一份新产物，避免改完规则却被状态闸跳过。
PIPE_HASH=$(shasum -a 256 scripts/tts_local.py | awk '{print $1}')
HASH=$(printf '%s\n%s\n' "$SOURCE_HASH" "$PIPE_HASH" | shasum -a 256 | awk '{print $1}')
LAST_HASH=""
LAST_OUT=""
if [ -f "$STATE" ]; then
    LAST_HASH=$(awk -F '\t' 'NR==1 {print $1}' "$STATE")
    LAST_OUT=$(awk -F '\t' 'NR==1 {print $3}' "$STATE")
fi
if [ "$FORCE" != "1" ] && [ "$HASH" = "$LAST_HASH" ] && [ -n "$LAST_OUT" ] && [ -f "$LAST_OUT" ]; then
    echo "[skip] 该稿件已按同一哈希合成过：$SCRIPT"
    echo "OK $TODAY 同稿已存在，跳过重复合成 | $LAST_OUT"
    exit 0
fi

# 3. 今天已合成过就跳过
if ls output/audio/${TODAY}-research* >/dev/null 2>&1; then
    echo "[skip] $TODAY 已合成过调研稿音频"
    echo "OK $TODAY 已有调研音频，跳过"
    exit 0
fi

# 4. 互斥：已有 tts_local.py 在跑就不叠加（16G 机器跑不动两个）
if pgrep -f "tts_local.py" >/dev/null 2>&1; then
    echo "[skip] 已有 tts_local.py 在跑"
    echo "OK $TODAY 跳过（有合成在跑）"
    exit 0
fi

# 4.5 时长闸（2026-09-13 加）：只报不拦。一夜没稿可听比短更糟，但短要留痕。
HAN=$(python3 -c "
import re, sys
t = open(sys.argv[1], encoding='utf-8').read()
print(len(re.findall(r'[一-鿿]', t)))
" "$SCRIPT")
HAN_EST=$((HAN / 168))
echo "[info] 汉字 $HAN ｜ 预估 $HAN_EST 分钟（目标 8500-10500 汉字 ≈ 51-62 分钟）"
if [ "$HAN" -lt 8500 ]; then
    echo "[!] SHORT 偏短：$HAN 汉字 ≈ $HAN_EST 分钟，不到 8500 汉字（≈51 分钟）"
    echo "    → 这次是拆得浅，不是合成问题。下期按 DESIGN.md 3.1b「二次深读」补"
fi

# 5. 从源文件名提取主题：2026-09-12-gemini-cli.md → gemini-cli
TOPIC=$(basename "$SCRIPT" .md)
TOPIC="${TOPIC#[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-}"   # 去日期前缀
TOPIC="${TOPIC%-breakdown}"                                     # 去 -breakdown 后缀

# 6. 真跑
OUT="output/audio/${TODAY}-research-${TOPIC}.m4a"
echo "[run] 合成 $SCRIPT -> $OUT"
ABS=$(cd "$(dirname "$SCRIPT")" && pwd)/$(basename "$SCRIPT")
DENOISE="$DENOISE" bash scripts/pipeline.sh tts-local "$ABS" "$OUT"
RC=$?
echo "[done] exit=$RC"

if [ $RC -ne 0 ]; then
    echo "FAILED 合成失败 exit=$RC，完整报错见上"
    exit $RC
fi

SECS=$(afinfo "$OUT" 2>/dev/null | awk '/estimated duration/ {print $3}')
MIN=$(awk -v s="${SECS:-0}" 'BEGIN{printf "%.0f", s/60}')
if [ "$MIN" -lt 45 ]; then
    echo "OK $TODAY 合成完成 | $OUT | ${MIN}分钟 ｜ SHORT 偏短（目标 51-62 分钟）"
else
    echo "OK $TODAY 合成完成 | $OUT | ${MIN}分钟"
fi
printf '%s\t%s\t%s\t%s\n' "$HASH" "$SCRIPT" "$OUT" "$(date '+%F %T')" > "$STATE"

# 7. 合成成功 → 自动上传网易云云盘（保持原文件名；本地产物始终保留）
UPLOAD_LOG=/tmp/research-synth-upload.log
echo "[run] 上传网易云：$OUT"
if bash scripts/pipeline.sh upload-local "$OUT" >"$UPLOAD_LOG" 2>&1; then
    echo "OK $TODAY 已上传网易云 | $OUT"
else
    echo "[warn] 网易云上传失败，音频保留在本地 output/audio/：$OUT"
    tail -20 "$UPLOAD_LOG"
fi
} 2>&1 | tee -a "$LOG"
