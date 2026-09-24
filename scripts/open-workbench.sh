#!/usr/bin/env bash
# 一键打开拆解工作台（http://127.0.0.1:8788/）
# 用法：bash scripts/open-workbench.sh
#   - 已在跑 → 直接开浏览器
#   - 没在跑 → 后台拉起服务，写日志到 output/workbench-server.log，再开浏览器

set -u
cd "$(dirname "$0")/.."   # 切到项目根目录

PORT=8788
URL="http://127.0.0.1:${PORT}/"
LOG="output/workbench-server.log"
PY="${PYTHON_BIN:-$(command -v python3 || echo python3)}"

# 探测端口是否已有服务在听（避免误判别的进程占着 8788）
probe() {
  curl -s -o /dev/null -m 2 "http://127.0.0.1:${PORT}/"
}

if probe; then
  echo "工作台已在运行：${URL}"
else
  echo "启动工作台..."
  nohup "${PY}" scripts/workbench_server.py --port "${PORT}" >> "${LOG}" 2>&1 &
  # 最多等 5 秒起服务
  for _ in 1 2 3 4 5; do
    if probe; then break; fi
    sleep 1
  done
  if probe; then
    echo "已启动（日志：${LOG}）"
  else
    echo "启动失败，看日志：tail -20 ${LOG}" >&2
    exit 1
  fi
fi

open "${URL}"
