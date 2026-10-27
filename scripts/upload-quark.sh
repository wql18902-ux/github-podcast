#!/bin/bash
# 播客成品音频备份到夸克网盘——网易云扫码登录过期、后台重登没人扫码时的第二落点。
#
# 用法：
#   bash scripts/upload-quark.sh <本地文件>       上传到夸克根目录 "/<文件名>"
#   bash scripts/upload-quark.sh --set-cookie     从 stdin 粘贴整段 Cookie，存进 Keychain 并验证
#   bash scripts/upload-quark.sh --delete-cookie  删掉 Keychain 里的 Cookie（换号 / 反向验证用）
#   bash scripts/upload-quark.sh --help           显示本段说明
#
# Cookie = 完整登录态，只进 macOS Keychain 通用密码（服务名见下方 KEYCHAIN_SERVICE），
# 不写任何文件、不进日志、不进 git。唯一人肉步骤：浏览器登录 pan.quark.cn，F12 复制整段 Cookie。
#
# 退出码：0 成功 | 1 上传失败（已写日志 + 推飞书告警）| 2 用法错 / Cookie 未配置
set -euo pipefail
cd "$(dirname "$0")/.."

KEYCHAIN_SERVICE="ai-jarvis-quark-cookie"
KUKE_BIN="bin/kuake"
QUARK_LOG="output/upload-quark.log"

usage() {
    cat <<'EOF'
用法：
  bash scripts/upload-quark.sh <本地文件>        上传到夸克网盘 /播客备份/ 目录（文件夹不存在会自动建）
  bash scripts/upload-quark.sh --set-cookie      从 stdin 粘贴 pan.quark.cn 整段 Cookie（Ctrl-D 结束），存 Keychain 并验证
  bash scripts/upload-quark.sh --delete-cookie   删掉 Keychain 里的 Cookie（换号 / 反向验证用）
  bash scripts/upload-quark.sh --help            显示本段说明

Cookie 只存 macOS Keychain，不落文件。上传成功 = kuake 退出码 0 且输出 JSON 含 "success": true。
退出码：0 成功 | 1 上传失败（写 output/upload-quark.log + 推飞书告警）| 2 用法错 / Cookie 未配置。
EOF
}

# ---- --set-cookie：stdin 读整段 Cookie → Keychain（-U 覆盖旧值），顺手验证登录态 ----
if [ "${1:-}" = "--set-cookie" ]; then
    echo "粘贴 pan.quark.cn 登录后的整段 Cookie（浏览器 F12 → Network → 任一请求的 Cookie 请求头），Ctrl-D 结束："
    cookie="$(cat)"
    cookie="${cookie#"${cookie%%[![:space:]]*}"}"   # 去首部空白（pbpaste / 粘贴常带尾随换行）
    cookie="${cookie%"${cookie##*[![:space:]]}"}"   # 去尾部空白
    if [ -z "$cookie" ]; then
        echo "[✗] 读到的 Cookie 是空的，没有写入 Keychain" >&2
        exit 2
    fi
    security add-generic-password -U -s "$KEYCHAIN_SERVICE" -a "$USER" -w "$cookie"
    echo "[✓] Cookie 已写入 macOS Keychain，开始验证登录态…"
    if KUAKE_COOKIE="$cookie" KUAKE_LOAD_DOTENV=0 "$KUKE_BIN" user >/dev/null 2>&1; then
        echo "[✓] 登录态有效，可以直接传了"
        exit 0
    fi
    echo "[!] 已存入，但登录态验证没过——Cookie 可能不完整（只复制了一部分）或已失效，重新复制后再 --set-cookie 一次" >&2
    exit 1
fi

# ---- --delete-cookie：删 Keychain 条目（反向验证 / 换号）----
if [ "${1:-}" = "--delete-cookie" ]; then
    if security delete-generic-password -s "$KEYCHAIN_SERVICE" >/dev/null 2>&1; then
        echo "[✓] 已删除 Keychain 里的 Cookie 条目"
        exit 0
    fi
    echo "[i] Keychain 里本来就没有这条 Cookie，没什么可删" >&2
    exit 1
fi

case "${1:-}" in
    --help|-h) usage; exit 0 ;;
esac

if [ $# -ne 1 ]; then
    echo "[✗] 参数不对：只需要一个本地文件路径" >&2
    usage >&2
    exit 2
fi
file="$1"
[ -f "$file" ] || { echo "[✗] 文件不存在：$file" >&2; exit 2; }

# Cookie 只从 Keychain 读；读不到就明说去配，不试 .env、不裸跑
cookie="$(security find-generic-password -s "$KEYCHAIN_SERVICE" -w 2>/dev/null || true)"
if [ -z "${cookie// /}" ]; then
    echo "[✗] 未配置夸克 Cookie（macOS Keychain 里读不到）" >&2
    echo "    配置：浏览器登录 pan.quark.cn → F12 复制整段 Cookie → 跑 bash scripts/upload-quark.sh --set-cookie 粘贴" >&2
    exit 2
fi

remote="/播客备份/$(basename "$file")"
# 目标文件夹不在就地建上（create 对已存在的目录会报错，属预期，吞掉这一种）
KUAKE_COOKIE="$cookie" KUAKE_LOAD_DOTENV=0 "$KUKE_BIN" create "播客备份" "/" >/dev/null 2>&1 || true
echo "==> 上传夸克网盘：$file → $remote"

# kuake：进度走 stderr，结果 JSON 走 stdout（见 docs/cli.md）；KUAKE_LOAD_DOTENV=0 防止误吃项目里的 .env
rc=0
json_out="$(KUAKE_COOKIE="$cookie" KUAKE_LOAD_DOTENV=0 "$KUKE_BIN" upload "$file" "$remote")" || rc=$?

# 判成功只认两条同时成立：退出码 0 且 JSON 的 success 为 true（防作弊口径，不许放宽）
# 注意：macOS 自带 bash 3.2 会把 $var 后面的多字节字符吃进变量名——变量后紧跟中文一律写 ${var}
verdict="$(printf '%s' "$json_out" | python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except ValueError:
    sys.stdout.write("BADJSON\n")
    sys.exit(0)
if data.get("success") is True:
    sys.stdout.write("OK\n")
else:
    msg = data.get("message") or data.get("error") or "未给出错误原因"
    sys.stdout.write("FAIL %s\n" % str(msg).replace("\n", " ")[:200])
')"

if [ "$rc" -eq 0 ] && [ "$verdict" = "OK" ]; then
    echo "[✓] 夸克上传成功：${remote}"
    mkdir -p "$(dirname "$QUARK_LOG")"
    printf '%s %s OK\n' "$(date '+%F %H:%M')" "$(basename "$file")" >> "$QUARK_LOG"
    exit 0
fi

# 失败：错误行只取 kuake 的 message/error 字段，绝不外带 Cookie
case "$verdict" in
    FAIL*)  err="${verdict#FAIL }" ;;
    OK*)    err="kuake 退出码 ${rc}（JSON 说成功但退出码非 0，按失败处理）" ;;
    *)      err="kuake 退出码 ${rc}，且输出不是有效 JSON" ;;
esac
echo "[✗] 夸克上传失败：${file}（${err}）" >&2
mkdir -p "$(dirname "$QUARK_LOG")"
printf '%s %s FAIL\n' "$(date '+%F %H:%M')" "$(basename "$file")" >> "$QUARK_LOG"
# 告警挂了自己记一句，绝不因为告警失败影响主流程
if ! python3 -m agent.notify --text "夸克上传失败：${file}（${err}）"; then
    echo "[!] 飞书告警也没发出去：${file}（${err}）" >&2
fi
exit 1
