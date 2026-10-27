#!/bin/bash
# github-podcast 每期固定流程编排
# 用法：scripts/pipeline.sh <子命令>
#   fetch           只跑信息源（带失败闸门）
#   pick            只跑选料
#   prep            fetch + pick（新一天开工用）
#   synth [日期]    TTS 合成当日文稿 + 时长验收（需 DOUBAO_TTS_KEY）
#   synth-local [日期]  VoxCPM2 本地 TTS 合成当日文稿（无需 API key）
#   synth-mimo [日期]   MiMo VoiceClone 云合成当日文稿（克隆音色，无需本地 GPU）
#   tts-mimo <文件> [输出]  任意文本(md) MiMo 克隆音合成 m4a
#   tts <文件> [输出] [atempo]  任意文本(txt/md)一键合成 mp3
#   tts-local <文件> [输出]  任意文本(txt/md)本地 TTS 一键合成 m4a
#   verify [文件]   单独验时长（太短才拦，不设目标值）
#   send [文件] [--dry-run]  发成品到自己飞书
#   upload [文件]   上传成品到网易云 + 夸克网盘双备份（保持原文件名）
#   upload-local [文件]  上传本地链路成品到网易云 + 夸克网盘（文件名带 -local）
# 写稿不在本脚本内——现在由 scripts/daily-prepare.sh 的夜班 agent 自动跑（首选入口，见 定时任务.md）。
# 本脚本保留作手动细分步骤：单独跑 fetch/pick、走旧 API 合成（synth/tts）、发飞书（send）、上传双云盘（upload）。
set -euo pipefail
cd "$(dirname "$0")/.."

# ncm-cli / lark-cli 装在 ~/.npm-global/bin，只有登录 shell 的 PATH 才带。
# cron / launchd 默认没有 → 显式补上，否则 upload/send 会静默「command not found」。
export PATH="$HOME/.npm-global/bin:$PATH"

NO_PROXY=(env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY)
TODAY=$(date +%F)
# 期号按 output/episodes/ep<N>-*/ 目录名算，**不按 episodes.log 行数**——log 一行一个仓库,
# 63 行 ≠ 63 期（2026-10-04 修；口径同 agent/state.py:141-157，守卫 tests/test_ep_next_no.py）。
# 只用于**产物文件名的缺省值**；对已存在的音频文件仍显式传路径，别让期号变化影响它。
EP_N=$(python3 scripts/ep_no.py)
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
    # 2026-10-21：user 身份缺 im:message.send_as_user（lark-cli 报 missing_scope），
    # 改用 bot 身份发给自己；bot 侧权限现成可用。要换回 user 身份先跑
    # `lark-cli auth login --scope "im:message.send_as_user"`。
    # lark-cli 的 --file 只收 cwd 相对路径（绝对路径与 .. 会被拒），先归一。
    local send_path="$file"
    case "$send_path" in
        /*) send_path=$(python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1]))' "$file") ;;
    esac
    "${NO_PROXY[@]}" lark-cli im +messages-send --as bot \
        --user-id "$uid" --file "$send_path" ${extra[@]+"${extra[@]}"}
}

cmd_upload() {
    local file="${1:-output/audio/${TODAY}-ep${EP_N}.mp3}"
    [ -f "$file" ] || { echo "[✗] 不存在：$file" >&2; exit 1; }
    echo "==> [4/4] 上传网易云云盘（保持原文件名）：$file"
    local ok=0
    # ncm-cli 裸跑失败会带着 set -e 崩脚本（2026-10-01 起扫码登录天天挂）；显式分支，不用 || true 吞状态
    if "${NO_PROXY[@]}" ncm-cli cloudupload upload "$file"; then
        ok=1
        echo "[✓] 网易云上传完成：$file"
    else
        echo "[!] 网易云上传失败（登录过期/二维码 300 秒无人扫）：$file" >&2
    fi
    # 第二落点：夸克网盘（见 docs/夸克备份.md）。网易云成没成都传——两块都没传上才算这步失败
    echo "==> 备份到夸克网盘：$file"
    if bash scripts/upload-quark.sh "$file"; then
        ok=1
    fi
    [ "$ok" = 1 ] || { echo "[✗] 网易云和夸克都没上传成功：$file" >&2; exit 1; }
}

cmd_upload_local() {
    # 本地链路产物（文件名带 -local）上传网易云，跟豆包产物区分开。
    local file="${1:-output/audio/${TODAY}-ep${EP_N}-local.m4a}"
    [ -f "$file" ] || { echo "[✗] 不存在：$file" >&2; exit 1; }
    echo "==> 上传网易云云盘（本地链路，保持原文件名）：$file"
    local ok=0
    if "${NO_PROXY[@]}" ncm-cli cloudupload upload "$file"; then
        ok=1
        echo "[✓] 网易云上传完成（本地链路）：$file"
    else
        echo "[!] 网易云上传失败（登录过期/二维码 300 秒无人扫）：$file" >&2
    fi
    # 第二落点：夸克网盘（见 docs/夸克备份.md）
    echo "==> 备份到夸克网盘：$file"
    if bash scripts/upload-quark.sh "$file"; then
        ok=1
    fi
    [ "$ok" = 1 ] || { echo "[✗] 网易云和夸克都没上传成功：$file" >&2; exit 1; }
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

cmd_tts_mimo() {
    local input="${1:?用法: tts-mimo <输入.txt|.md> [输出.m4a]}"
    local out="${2:-/tmp/tts_mimo_out.m4a}"
    [ -f "$input" ] || { echo "[✗] 输入不存在：$input" >&2; exit 1; }
    echo "==> MiMo 克隆音合成：$input -> ${out}（语速 ${MIMO_HAN_PER_MIN:-0=原速} 汉字/分）"
    # 不经 NO_PROXY：cloud_tts._opener() 已显式直连，绕开失效的 7890
    python3 scripts/tts_mimo.py --input "$input" --output "$out" \
        --han-per-min "${MIMO_HAN_PER_MIN:-0}"
    local secs
    secs=$(afinfo "$out" | awk '/estimated duration/ {print $3}')
    echo "[✓] 完成：${out}，时长 ${secs%%.*}s"
}

cmd_synth_mimo() {
    local date="${1:-$TODAY}"
    local script="output/${date}-script.md"
    local out="output/audio/${date}-ep${EP_N}-mimo.m4a"
    [ -f "$script" ] || { echo "[✗] 文稿不存在：$script" >&2; exit 1; }
    echo "==> [3/4] MiMo VoiceClone 合成 ep${EP_N}（克隆音色 voices/mimo-clone-ref.wav，语速 ${MIMO_HAN_PER_MIN:-0=原速} 汉字/分）"
    python3 scripts/tts_mimo.py --input "$script" --output "$out" \
        --han-per-min "${MIMO_HAN_PER_MIN:-0}"
    cmd_verify "$out"
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
    synth-mimo) shift; cmd_synth_mimo "${1:-}" ;;
    tts)    shift; cmd_tts "${1:-}" "${2:-}" "${3:-}" ;;
    tts-local) shift; cmd_tts_local "${1:-}" "${2:-}" ;;
    tts-mimo) shift; cmd_tts_mimo "${1:-}" "${2:-}" ;;
    verify) shift; cmd_verify "${1:-}" ;;
    send)   shift; cmd_send "${1:-}" "${2:-}" ;;
    upload) shift; cmd_upload "${1:-}" ;;
    upload-local) shift; cmd_upload_local "${1:-}" ;;
    *)      usage ;;
esac
