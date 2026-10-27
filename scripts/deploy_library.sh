#!/usr/bin/env bash
# 把 web/library 整目录发到 GitHub Pages（公开仓 wql18902-ux/sourcecast）。
#
# 为什么是「整目录 + 排除」而不是白名单（2026-10-27 改）：
#   旧版按十来个文件名 cp，站点后来加了 experience.js / knowledge.js /
#   personal.js / rail.js / griffin.css 等，全没跟上，线上一直停在 2026-10-24 的
#   旧版「知栈·判断库」。白名单漏一个就静默缺件；排除式漏一个只会多带一个无害
#   文件，而且漏了会被下面第 4 步的线上自检当场抓住。
#
# Pages 是 legacy build（main 分支根目录），推上去就发布，不需要 Actions。
# Pages CDN 实测对 bytes=0-99 回 206，所以线上不需要 serve.py；serve.py 只在
# 本地预览时给不透传 Range 的服务补 206。
#
# 用法：
#   bash scripts/deploy_library.sh                 # 同步 + 提交 + 推送 + 线上自检
#   bash scripts/deploy_library.sh "说明文字"       # 同上，指定提交说明
#   bash scripts/deploy_library.sh --dry-run       # 只同步到临时目录，不推
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

SRC="web/library"
REPO="wql18902-ux/sourcecast"
BASE="https://wql18902-ux.github.io/sourcecast/"
NET="env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY"

DRY=0
MSG="更新页声站点"
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY=1 ;;
        *) MSG="$arg" ;;
    esac
done

[ -f "$SRC/index.html" ] || { echo "[✗] 找不到 $SRC/index.html" >&2; exit 2; }

# ── 1. 本地预检：引用齐全 + 没有云依赖残留 ──────────────────────────
echo "==> [1/4] 本地预检"
missing=0
while IFS= read -r f; do
    case "$f" in
        http*|data:*|""|\#*) continue ;;
    esac
    f="${f%%\?*}"
    [ -e "$SRC/$f" ] || { echo "[✗] index.html 引用了不存在的文件：${f}" >&2; missing=1; }
done < <(grep -oE '(href|src)="[^"]+"' "$SRC/index.html" | sed -E 's/.*="([^"]+)"/\1/')
[ "$missing" -eq 0 ] || exit 1

if grep -qE 'cloud-sdk\.js|data/cloud\.js' "$SRC/index.html"; then
    echo "[✗] index.html 还引用着平台云 SDK（data/cloud.js 或 vendor/cloud-sdk.js）" >&2
    echo "    站点已不接外部云服务，先清掉这两行再发。" >&2
    exit 1
fi
echo "    ✓ 引用齐全，无云 SDK 残留"

# ── 2. 浅克隆公开仓（不碰任何本地仓） ──────────────────────────────
echo "==> [2/4] 浅克隆 ${REPO}"
STAGE="$(mktemp -d /tmp/sourcecast-deploy-XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT
$NET git clone -q --depth 1 "https://github.com/$REPO.git" "$STAGE/repo"

# ── 3. 整目录同步（排除内部文档 / 构建包 / 平台身份 / 本地服务） ────
# 注意 --exclude='.git/' 不是可选项：--delete 会把目标仓的 .git 一起删掉
# （照抄 publish-oss.sh 2026-09-24 踩过的坑）。
echo "==> [3/4] 同步 ${SRC} → 公开仓"
rsync -a --delete \
    --exclude='.git/' \
    --exclude='.DS_Store' \
    --exclude='README.md' \
    --exclude='DESIGN.md' \
    --exclude='*.zip' \
    --exclude='dist/' \
    --exclude='output/' \
    --exclude='.wbapp_*' \
    --exclude='*.genie' \
    --exclude='*/applications.yaml' \
    --exclude='serve.py' \
    "$SRC"/ "$STAGE/repo"/

# .nojekyll 必须留：否则 Pages 会跑 Jekyll，下划线开头的资源可能被吞
touch "$STAGE/repo/.nojekyll"

if grep -rqE 'WorkBuddyCloud|data/cloud\.js|vendor/cloud-sdk\.js' "$STAGE/repo" --include='*.js' --include='*.html' 2>/dev/null; then
    echo "[✗] 待发布内容里还有云 SDK 调用，先清干净（站点不该依赖别人的服务）" >&2
    exit 1
fi

cd "$STAGE/repo"
git add -A
if git diff --cached --quiet; then
    echo "    [skip] 内容没有变化"
else
    git -c user.name="wql18902-ux" -c user.email="noreply@github-podcast.local" \
        commit -q -m "$MSG"
    echo "    提交：$(git rev-parse --short HEAD) ${MSG}"
fi

if [ "$DRY" -eq 1 ]; then
    echo "    --dry-run：不推送。待发文件数 $(git ls-files | wc -l | tr -d ' ')"
    exit 0
fi

$NET git -c http.proxy= -c https.proxy= push -q origin HEAD:main
echo "    已推送 → https://github.com/${REPO}"

# ── 4. 线上自检（Pages 构建有延迟，轮询到新版本） ───────────────────
echo "==> [4/4] 线上自检"
LOCAL_TITLE=$(grep -oE '<title>[^<]*' "$ROOT/$SRC/index.html" | head -1 | sed 's/<title>//')
echo "    期望标题：${LOCAL_TITLE}"
ok=0
for i in $(seq 1 24); do
    body=$($NET curl -s --http1.1 -m 20 "${BASE}?deploy=$(date +%s)" || true)
    if printf '%s' "$body" | grep -qF "$LOCAL_TITLE"; then ok=1; break; fi
    sleep 5
done
if [ "$ok" -eq 1 ]; then
    echo "    ✓ 线上标题已更新（等了 $(( (i-1)*5 )) 秒）"
else
    echo "    [✗] 线上标题还没更新（已等 120 秒），查 Pages 构建状态：" >&2
    echo "        ${NET} gh api repos/${REPO}/pages" >&2
    exit 1
fi

fail=0
for f in app.js data.js studio.js experience.js knowledge.js personal.js rail.js vendor/lwq/components.js; do
    code=$($NET curl -s -o /dev/null -w '%{http_code}' --http1.1 -m 20 "${BASE}${f}?c=$(date +%s)")
    [ "$code" = "200" ] || { echo "    [✗] ${f} → HTTP ${code}" >&2; fail=1; }
done
[ "$fail" -eq 0 ] && echo "    ✓ 关键 JS 全部 200"

AUDIO=$($NET curl -s --http1.1 -m 20 "${BASE}data/finished-audio.js?c=$(date +%s)" \
    | grep -oE '"src": *"[^"]+"' | head -1 | sed -E 's/.*"([^"]+)"$/\1/')
if [ -n "$AUDIO" ]; then
    code=$($NET curl -s -o /dev/null -w '%{http_code}' -r 0-99 --http1.1 -m 20 "${BASE}${AUDIO}")
    if [ "$code" = "206" ]; then
        echo "    ✓ 音频 Range 请求 → 206（${AUDIO}）"
    else
        echo "    [✗] 音频 Range 请求 → HTTP ${code}（拖动会退化）" >&2
        fail=1
    fi
fi

# 旧构建包不该还能下载
for gone in sourcecast-workbuddy.zip; do
    code=$($NET curl -s -o /dev/null -w '%{http_code}' --http1.1 -m 20 "${BASE}${gone}")
    [ "$code" = "404" ] || echo "    [!] ${gone} 仍可访问（HTTP ${code}），确认是否有意保留"
done

[ "$fail" -eq 0 ] || exit 1
echo
echo "[✓] 已发布：${BASE}"
echo "    线上文件数：$(git ls-files | wc -l | tr -d ' ')"
