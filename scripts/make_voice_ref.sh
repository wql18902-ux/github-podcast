#!/bin/bash
# 任意音视频 → 克隆参考音频（+ 转写文本）
# 用法: make_voice_ref.sh <输入音视频> <输出名> [起始秒] [时长秒]
set -euo pipefail
IN="${1:?用法: make_voice_ref.sh <输入> <输出名> [start] [dur]}"
NAME="${2:?缺输出名}"
SS="${3:-0}"; DUR="${4:-18}"
OUTDIR=~/ai-brain/github-podcast/voices
OUT="$OUTDIR/$NAME.wav"

# 1) 抽音频 + 转单声道 48k（克隆统一格式）
ffmpeg -y -v error -ss "$SS" -t "$DUR" -i "$IN" -ac 1 -ar 48000 -c:a pcm_s16le "$OUT"

# 2) 响度规范化到 -20 LUFS / 峰值 -3 dBTP（留余量，因为模型会放大）
#    ⚠️ 不要用 volume=+6dB 这种拍脑袋做法，会喂给模型一个过热的参考
ffmpeg -y -v error -i "$OUT" -af "loudnorm=I=-20:TP=-3:LRA=11" \
  -ac 1 -ar 48000 -c:a pcm_s16le "$OUT.norm.wav"
mv "$OUT.norm.wav" "$OUT"

# 3) 输出体检
ffmpeg -hide_banner -v info -i "$OUT" -af astats -f null - 2>&1 \
  | grep -E "Peak level dB|RMS level dB" | tail -2
#    响度核对：目标 I = -20 LUFS（loudnorm 单程动态模式，峰值不保证正好 -3，实测常落在 -4~-6）
ffmpeg -hide_banner -v info -i "$OUT" -af ebur128=peak=true -f null - 2>&1 \
  | grep -A4 "Summary" | grep -E "I:|Peak:" | tail -2
echo "[✓] 参考音频: $OUT"
echo "下一步：用 sensevoice-onnx skill 转写它，把文本写成 $OUTDIR/$NAME.txt（终极克隆必需）"
