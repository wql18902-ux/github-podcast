#!/bin/bash
# 周选题 cron 入口（Trae 每周日 21:00 调）：给常驻工作台服务发一条入队请求。
# 服务没起 / 入队失败：追加日志 + 非 0 退出码，不静默。
# 确认动作保留人工：跑完后去选题台页面勾选确认，脚本不代确认。
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/output/selection-tasks/weekly-enqueue.log"
mkdir -p "$(dirname "$LOG")"
ts() { date '+%F %T'; }

resp=$(curl -s -m 15 -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8788/api/weekly-tasks 2>&1)
code=$?
if [ $code -ne 0 ]; then
  echo "[$(ts)] curl 失败 exit=$code（服务多半没起，先 launchctl kickstart -k gui/\$(id -u)/com.github-podcast.workbench）：$resp" >> "$LOG"
  exit 1
fi
echo "[$(ts)] $resp" >> "$LOG"
if echo "$resp" | grep -q '"ok": *true'; then
  echo "[$(ts)] 入队成功，跑完去选题台确认" >> "$LOG"
else
  echo "[$(ts)] 返回不含 ok=true，视为失败" >> "$LOG"
  exit 1
fi
