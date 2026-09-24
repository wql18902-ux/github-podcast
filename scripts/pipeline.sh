#!/bin/bash
# github-podcast 每期固定流程编排
# 用法：scripts/pipeline.sh <子命令>
#   fetch           只跑信息源（带失败闸门）
#   pick            只跑选料
#   prep            fetch + pick（新一天开工用）
#   synth [日期]    TTS 合成当日文稿 + 时长验收（需 DOUBAO_TTS_KEY）
#   synth-local [日期]  VoxCPM2 本地 TTS 合成当日文稿（无需 API key）
#   tts <文件> [输出] [atempo]  任意文本(txt/md)一键合成 mp3
#   tts-local <文件> [输出]  任意文本(txt/md)本地 TTS 一键合成 m4a
#   verify [文件]   单独验时长（太短才拦，不设目标值）
#   send [文件] [--dry-run]  发成品到自己飞书
#   upload [文件]   上传成品到网易云云盘（保持原文件名）
#   upload-local [文件]  上传本地链路成品到网易云（文件名带 -local）
# 写稿不在本脚本内——现在由 scripts/daily-prepare.sh 的夜班 agent 自动跑（首选入口，见 定时任务.md）。
# 本脚本保留作手动细分步骤：单独跑 fetch/pick、走旧 API 合成（synth/tts）、发飞书（send）、上传网易云（upload）。
set -euo pipefail
cd "$(dirname "$0")/.."

# ncm-cli / lark-cli 装在 ~/.npm-global/bin，只有登录 shell 的 PATH 才带。
# cron / launchd 默认没有 → 显式补上，否则 upload/send 会静默「command not found」。
export PATH="$HOME/.npm-global/bin:$PATH"

NO_PROXY=(env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY)
TODAY=$(date +%F)
EP_N=$(wc -l < output/episodes.log | tr -d ' ')
# 时长不设目标值，只设「疑似太短」的复核线。长短由素材厚度决定，不硬凑。
# 单期要调整用环境变量覆盖：MIN_SEC=1200 scripts/pipeline.sh synth
MIN_SEC=${MIN_SEC:-1800}    # 30 分钟：低于此判为没讲透 / 漏了 atempo，硬拦
SOFT_SEC=${SOFT_SEC:-2700}  # 45 分钟：低于此只提示，不拦（素材薄也正常）

cmd_fetch() {
    echo "==> [1/4] fetch.py 信息源"
    local log=/tmp/podcast_fetch_$$.log
    if ! "${NO_PROXY[@]}" python3 fetch.py > "$log" 2>&1; then
        cat "$log"; rm -f "$log"
        echo "[✗] fetch.py 异常退出" >&2; exit 1
    fi
    cat "$log"
    local ok fail
    ok=$(grep -c '^\[[.]\]' "$log" || true)
    fail=$(grep -c '查询失败' "$log" || true)
    rm -f "$log"
    if [ "$ok" -eq 0 ]; then
        echo "[✗] 全部查询失败（多半是代理/网络），当日 md 不可信，勿使用" >&2
        exit 1
    fi
    if [ "$fail" -gt 0 ]; then
        echo "[!] 有 $fail 个查询失败，清单不完整，建议重跑" >&2
    fi
}

cmd_pick() {
    echo "==> [2/4] episode.py 选料"
    "${NO_PROXY[@]}" python3 scripts/episode.py
    echo ""
    echo "==> 下一步：bash scripts/daily-prepare.sh 会让夜班 agent 读源码写稿（首选）"
    echo "    若手写稿：口径照 output/podcast-01 样板 + DESIGN.md 第四节；讲透为止，不设字数目标"
    echo "    撑不起一期就回当日清单挑 1-2 个同主题项目拼盘（最多 3 个），别注水凑字"
}

cmd_verify() {
    local file="${1:-output/audio/${TODAY}-ep${EP_N}.mp3}"
    [ -f "$file" ] || { echo "[✗] 不存在：$file" >&2; exit 1; }
    local secs
    secs=$(afinfo "$file" | awk '/estimated duration/ {print $3}')
    secs=${secs%%.*}
    echo "==> 时长 ${secs}s / $((secs / 60)) 分钟: $file"
    if [ "$secs" -lt "$MIN_SEC" ]; then
        echo "[✗] 不足 $((MIN_SEC / 60)) 分钟——多半是稿子没写够或漏了 atempo，验收失败" >&2
        exit 1
    fi
    if [ "$secs" -lt "$SOFT_SEC" ]; then
        echo "[!] 短于 $((SOFT_SEC / 60)) 分钟，不拦；但请确认是素材本身薄，而不是没读透源码" >&2
    fi
    echo "[✓] 时长验收通过"
}

cmd_synth() {
    local date="${1:-$TODAY}"
    local script="output/${date}-script.md"
    local out="output/audio/${date}-ep${EP_N}.mp3"
    [ -f "$script" ] || { echo "[✗] 文稿不存在：$script" >&2; exit 1; }
    [ -n "${DOUBAO_TTS_KEY:-}" ] || {
        echo "[✗] 未设置 DOUBAO_TTS_KEY（只从环境变量读，内联注入）" >&2; exit 2; }
    echo "==> [3/4] TTS 合成 ep${EP_N}（atempo 0.72）"
    "${NO_PROXY[@]}" python3 scripts/tts.py \
        --input "$script" --output "$out" --atempo 0.72
    cmd_verify "$out"
}

cmd_send() {
    local file="${1:-output/audio/${TODAY}-ep${EP_N}.mp3}"
    local -a extra=()
    [ "${2:-}" = "--dry-run" ] && extra+=(--dry-run)
    [ -f "$file" ] || { echo "[✗] 不存在：$file" >&2; exit 1; }
    echo "==> [4/4] 发飞书 ${extra[*]:-}"
    local uid
    uid=$("${NO_PROXY[@]}" lark-cli contact +get-user \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["user"]["open_id"])')
    "${NO_PROXY[@]}" lark-cli im +messages-send \
        --user-id "$uid" --file "$file" "${extra[@]}"
}

cmd_upload() {
    local file="${1:-output/audio/${TODAY}-ep${EP_N}.mp3}"
    [ -f "$file" ] || { echo "[✗] 不存在：$file" >&2; exit 1; }
    echo "==> [4/4] 上传网易云云盘（保持原文件名）：$file"
    "${NO_PROXY[@]}" ncm-cli cloudupload upload "$file"
}

cmd_upload_local() {
    # 本地链路产物（文件名带 -local）上传网易云，跟豆包产物区分开。
    local file="${1:-output/audio/${TODAY}-ep${EP_N}-local.m4a}"
    [ -f "$file" ] || { echo "[✗] 不存在：$file" >&2; exit 1; }
    echo "==> 上传网易云云盘（本地链路，保持原文件名）：$file"
    "${NO_PROXY[@]}" ncm-cli cloudupload upload "$file"
}

cmd_tts() {
    local input="${1:?用法: tts <输入.txt|.md> [输出.mp3] [atempo，默认1.0]}"
    local out="${2:-/tmp/tts_out.mp3}"
    local atempo="${3:-1.0}"
    [ -f "$input" ] || { echo "[✗] 输入不存在：$input" >&2; exit 1; }
    [ -n "${DOUBAO_TTS_KEY:-}" ] || {
        echo "[✗] 未设置 DOUBAO_TTS_KEY（只从环境变量读，内联注入）" >&2; exit 2; }
    echo "==> TTS 合成：$input -> $out (atempo $atempo)"
    "${NO_PROXY[@]}" python3 scripts/tts.py \
        --input "$input" --output "$out" --atempo "$atempo"
    local secs
    secs=$(afinfo "$out" | awk '/estimated duration/ {print $3}')
    echo "[✓] 完成：${out}，时长 ${secs%%.*}s"
}

cmd_synth_local() {
    local date="${1:-$TODAY}"
    local script="output/${date}-script.md"
    local out="output/audio/${date}-ep${EP_N}-local.m4a"
    [ -f "$script" ] || { echo "[✗] 文稿不存在：$script" >&2; exit 1; }
    echo "==> [3/4] 本地 TTS 合成 ep${EP_N}（VoxCPM2 2B，M4 Metal，denoise=${DENOISE:-off}）"
    # DENOISE 环境变量透传降噪档位：off / deesser（方案一）/ deesser-treble（方案二）
    python3 scripts/tts_local.py --input "$script" --output "$out" \
        --denoise "${DENOISE:-off}"
    cmd_verify "$out"
}

cmd_tts_local() {
    local input="${1:?用法: tts-local <输入.txt|.md> [输出.m4a]}"
    local out="${2:-/tmp/tts_local_out.m4a}"
    [ -f "$input" ] || { echo "[✗] 输入不存在：$input" >&2; exit 1; }
    echo "==> 本地 TTS 合成：$input -> ${out}（denoise=${DENOISE:-off}）"
    python3 scripts/tts_local.py --input "$input" --output "$out" \
        --denoise "${DENOISE:-off}"
    local secs
    secs=$(afinfo "$out" | awk '/estimated duration/ {print $3}')
    echo "[✓] 完成：${out}，时长 ${secs%%.*}s"
}

usage() {
    sed -n '2,15p' "$0"
}

case "${1:-help}" in
    fetch)  cmd_fetch ;;
    pick)   cmd_pick ;;
    prep)   cmd_fetch; cmd_pick ;;
    synth)  shift; cmd_synth "${1:-}" ;;
    synth-local) shift; cmd_synth_local "${1:-}" ;;
    tts)    shift; cmd_tts "${1:-}" "${2:-}" "${3:-}" ;;
    tts-local) shift; cmd_tts_local "${1:-}" "${2:-}" ;;
    verify) shift; cmd_verify "${1:-}" ;;
    send)   shift; cmd_send "${1:-}" "${2:-}" ;;
    upload) shift; cmd_upload "${1:-}" ;;
    upload-local) shift; cmd_upload_local "${1:-}" ;;
    *)      usage ;;
esac
