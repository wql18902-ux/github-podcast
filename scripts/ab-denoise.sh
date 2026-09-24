#!/bin/bash
# 本地 TTS 降噪两套方案 · 整期 A/B —— 手动对比用（2026-09-12 立）
#
# 干什么：拿同一份文稿，用两套降噪档各跑一遍整期，产出两条可对比的 m4a。
#   方案一：deesser 轻档        —— 推荐默认（句尾"滋"声 -0.8 → -15.9 dB，音色几乎无损）
#   方案二：deesser + 8k 高架   —— 更干净一点（再降 ~1.3 dB），代价高频细节略少
#
# 产物（默认拿 output/latest-script.md 当稿子）：
#   output/audio/<日期>-ep<N>-方案1-deesser.m4a
#   output/audio/<日期>-ep<N>-方案2-deesser-treble.m4a
#
# ⚠️ 必须一条一条跑，不能并行——两套共用 8083 端口，同时跑会打架。
# 用法：
#   bash scripts/ab-denoise.sh                  # 用 latest-script.md，日期取今天
#   bash scripts/ab-denoise.sh <文稿.md>        # 指定稿子
set -uo pipefail
cd "$(dirname "$0")/.." || exit 0
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.npm-global/bin:$PATH"

SCRIPT="${1:-output/latest-script.md}"
[ -f "$SCRIPT" ] || { echo "[✗] 文稿不存在：$SCRIPT" >&2; exit 1; }

TODAY=$(date +%F)
EP_N=$(wc -l < output/episodes.log 2>/dev/null | tr -d ' '); EP_N=${EP_N:-0}
OUT1="output/audio/${TODAY}-ep${EP_N}-方案1-deesser.m4a"
OUT2="output/audio/${TODAY}-ep${EP_N}-方案2-deesser-treble.m4a"
LOG=output/ab-denoise.log

echo "===== $(date '+%F %T') A/B 两套方案 =====" >> "$LOG"
echo "文稿：$SCRIPT" >> "$LOG"

run_one() {
    local tag="$1" out="$2" dn="$3"
    echo ""
    echo "==> ${tag}（denoise=${dn}）→ ${out}"
    echo "[run] $tag denoise=$dn -> $out" >> "$LOG"
    env -u PYTHONPATH python3 scripts/tts_local.py \
        --input "$SCRIPT" --output "$out" --denoise "$dn" >> "$LOG" 2>&1
    local rc=$?
    echo "[done] $tag exit=$rc" >> "$LOG"
    if [ $rc -ne 0 ]; then
        echo "[✗] ${tag} 失败（exit=$rc），日志见 $LOG" >&2
        return $rc
    fi
    echo "[✓] $tag 完成：$out"
}

run_one "方案一 deesser"        "$OUT1" "deesser"          || exit 1
run_one "方案二 deesser-treble" "$OUT2" "deesser-treble"   || exit 1

echo ""
echo "===== 两套都完成 ====="
echo "方案一：$OUT1"
echo "方案二：$OUT2"
echo "听重点：句尾'滋'声还在不在 / 人声整体有没有变闷"
