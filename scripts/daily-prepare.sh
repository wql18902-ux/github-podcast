#!/bin/bash
# 每夜自动产出一期播客文稿：信息源 → 选料 → claude headless 拆解写稿 → 验收 → 落状态
#
# 手动跑：bash scripts/daily-prepare.sh
# 只跑到选料：PREP_ONLY=1 bash scripts/daily-prepare.sh（给「agent 自己写稿」的场景用，见下）
# 定时跑：WorkBuddy 定时任务「AI播客拆解写稿」，每天 22:00（2026-09-14 统一，此前三处口径不一致）
#
# v2 设计要点（2026-09-10，2026-09-14 修订）：
# - output/latest-status.txt 由 scripts/verify-episode.sh 统一写，写稿 agent 不许碰（会污染闸门）
# - 验收判据全部搬进 scripts/verify-episode.sh：拆解笔记字段数/字节数/实现级节/具体值密度/
#   时效两栏/黑名单，加上稿子汉字数。**字数不再是「不设下限」**——2026-09-13 他反馈一路滑到 23 分钟，
#   现在硬门 8500 汉字（≈51 分钟）、<6500 判失败。
# - 失败一律写 FAILED 并保留上一期旧稿，合成链路读到非 OK 就跳过，不会重录旧稿
# - PREP_ONLY=1 的存在理由：WorkBuddy 定时任务里是 agent 轮次，agent 跑一个 2-4 小时的脚本
#   会被 Bash 工具超时切成后台、随轮次结束被收掉。所以编排归脚本、写稿归 agent：
#   PREP_ONLY=1 bash daily-prepare.sh  →  agent 按 write-episode-prompt.md 写  →  verify-episode.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TODAY=$(date +%F)
STATUS=output/latest-status.txt
SCRIPT=output/latest-script.md
EPLOG=output/episodes.log
NO_PROXY=(env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY)
CLAUDE_BIN=$(command -v claude 2>/dev/null || echo claude)

fail() {
    printf 'FAILED %s %s\n' "$TODAY" "$1" > "$STATUS"
    echo "[✗] $1" >&2
    exit 1
}

count_lines() { [ -f "$1" ] && wc -l < "$1" | tr -d ' ' || echo 0; }

# 故意不做，不是失败：**不碰状态文件**（豆包还要靠那个 OK 去合成待消费的稿子），退出码 0
defer() {
    echo "[–] $1" >&2
    echo "===== $(date '+%F %T') 跳过本轮 ====="
    exit 0
}

# 待消费闸：上一期稿子写好了但还没被豆包合成，这轮就别写新稿——
# 一覆盖，那期的稿子就永远出不来音频了（dated 副本还在，但豆包只认 latest-script.md）。
# 判据：latest-script.md 比 output/audio/ 里最新成品还新 = 还没合成。
# 48 小时逃生门：豆包要是坏了好几天，不能因为一直没成品就把夜班永久卡死。
# 这道闸必须跑在 episode.py 之前——它一跑就会往 episodes.log 记账，等于把这期项目烧掉了。
NEWEST_AUDIO=$(ls -t output/audio/*.m4a 2>/dev/null | head -1)
if [ -n "${NEWEST_AUDIO:-}" ] && [ -f "$SCRIPT" ] && [ "$SCRIPT" -nt "$NEWEST_AUDIO" ]; then
    PENDING_AGE_H=$(( ( $(date +%s) - $(stat -f %m "$SCRIPT") ) / 3600 ))
    if [ "$PENDING_AGE_H" -lt 48 ] && head -1 "$STATUS" 2>/dev/null | grep -q '^OK'; then
        defer "上一期还没合成音频（latest-script.md 写于 ${PENDING_AGE_H}h 前，最新成品是 $(basename "$NEWEST_AUDIO")），不覆盖"
    fi
fi

echo "===== $(date '+%F %T') 第 ${TODAY} 期开工 ====="

echo "===== [1/4] 信息源 fetch ====="
FETCH_OUT=$("${NO_PROXY[@]}" python3 fetch.py 2>&1)
echo "$FETCH_OUT"
if echo "$FETCH_OUT" | grep -q '海外 0 个'; then
    fail "fetch 全失败，当日清单不可信"
fi
if echo "$FETCH_OUT" | grep -q '查询失败'; then
    echo "[!] 有查询失败，清单不完整，继续但选料面会窄" >&2
fi

# 国内大厂源（2026-09-11 加）：白名单制，只收 DeepSeek / 千问 / 字节 / 智谱。
# 写自己的 output/<日期>-cn-sources.md，**不碰 fetch.py 的 QUERIES/黑名单**（红线）。
# 失败不拦整期——这是外围增强，不是闸门。
echo "===== [1.5/4] 国内大厂源 fetch（外围，失败不拦） ====="
"${NO_PROXY[@]}" python3 scripts/fetch_cn_sources.py || echo "[!] 国内源抓取失败，本期只用海外池"

echo "===== [2/4] 选料 + clone ====="
"${NO_PROXY[@]}" python3 scripts/episode.py || fail "选料失败（episode.py 非零退出）"

# PREP_ONLY=1：只跑到选料为止，不调写稿 agent（2026-09-14 加）。
# 为什么需要：WorkBuddy 定时任务里是「agent 轮次」，agent 跑一个 2-4 小时的脚本会被 Bash 工具
# 超时切成后台、随后随轮次结束被收掉，撑不到写完。所以编排归脚本、写稿归 agent：
#   PREP_ONLY=1 bash scripts/daily-prepare.sh   →   agent 按 write-episode-prompt.md 写   →   verify-episode.sh
# 这样待消费闸、fetch 失败闸都还在脚本里，不用把编排抄进 prompt（抄两份迟早对不上）。
if [ "${PREP_ONLY:-0}" = "1" ]; then
    echo "[–] PREP_ONLY=1：选料完成，停在写稿前（写稿交给调用方）"
    echo "===== $(date '+%F %T') 收工（仅准备） ====="
    exit 0
fi

# 快照：用来判断写稿到底有没有产出新东西
BEFORE_MTIME=$(stat -f %m "$SCRIPT" 2>/dev/null || echo 0)
BEFORE_EP=$(count_lines "$EPLOG")

echo "===== [3/4] claude headless 拆解写稿 ====="
"$CLAUDE_BIN" -p "$(cat scripts/write-episode-prompt.md)" \
    --allowedTools "Read,Write,Edit,Bash,Glob,Grep" \
    --output-format text || fail "写稿 agent 非零退出"

echo "===== [4/4] 验收（闸门唯一入口：scripts/verify-episode.sh） ====="
[ -f "$SCRIPT" ] || fail "没有产出 latest-script.md"

AFTER_MTIME=$(stat -f %m "$SCRIPT" 2>/dev/null || echo 0)
if [ "$AFTER_MTIME" -le "$BEFORE_MTIME" ]; then
    fail "latest-script.md 没被更新（agent 没写，拦住豆包别重录旧稿）"
fi

# 验收逻辑 2026-09-14 全部抽到 scripts/verify-episode.sh。
# 为什么抽：以前闸门写在下面这几十行里，而写稿 agent 当时被 redirect 到 output/research/，
# 于是闸门守的是一条不产出稿子的路径，从未真正拦过任何东西。抽成独立入口后，
# 「写稿 agent 自己跑它」和「本脚本跑它」用同一份判据，不会再各说各话。
bash scripts/verify-episode.sh "$TODAY" || exit 1

echo "===== $(date '+%F %T') 收工 ====="
