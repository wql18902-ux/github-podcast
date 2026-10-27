#!/bin/bash
# 每期验收闸（唯一入口，拆解链路与手动链路共用）
#
# 用法：
#   bash scripts/verify-episode.sh            # 验今天
#   bash scripts/verify-episode.sh 2026-09-14 # 验指定日期
#
# 设计要点（2026-09-14 立，V2）：
# - 这是「闸门唯一入口」：写稿 agent 写完自己跑它，或由 daily-prepare.sh 调用。
#   以前闸门写在 daily-prepare.sh 里，但那条链路当时不产出稿子，等于闸门守死路。
# - 分钟换算统一按 175 汉字/分（2026-10-03 用户拍板，豆包 seed-audio 六样本实测散布
#   140-195 的中位偏保守取值；守卫测试 tests/test_speed_caliber.py，漂移史 BLOCKED.md）。
#   产出侧 PACE 4.0 ≈187 汉字/分是**合成档位**，不是预估口径，两者不互改。
#   闸门硬阈值 8500/6500 只跟「写没写够」有关，跟语速无关，别顺改。
# - 只读稿子、只写 output/latest-status.txt。不 clone、不 fetch、不合成。
# - 验收对象是「真落盘路径」：output/latest-script.md + output/<日期>-breakdown.md
# - 拆分两类判据：内容闸（读没读到实现级）与时长闸（写没写够）。前者先跑，
#   因为「没读源码」比「写得短」更根本。
set -uo pipefail

cd "$(dirname "$0")/.."

TODAY="${1:-$(date +%F)}"
STATUS=output/latest-status.txt
SCRIPT=output/latest-script.md
BREAKDOWN=output/${TODAY}-breakdown.md
EPLOG=output/episodes.log
BLACKLIST=scripts/blacklist-projects.txt

fail() {
    printf 'FAILED %s %s\n' "$TODAY" "$1" > "$STATUS"
    echo "[✗] $1" >&2
    exit 1
}

echo "===== 验收闸 · $TODAY ====="

# ---------- A 内容闸：读没读到实现级 ----------

[ -f "$SCRIPT" ] || fail "没产出 $SCRIPT"
[ -f "$BREAKDOWN" ] || fail "没写拆解笔记 ${BREAKDOWN}（跳过了逐文件读源码那步）"

BFIELDS=$(grep -cE '^## *[0-9]+[ .、]' "$BREAKDOWN")
BSIZE=$(wc -c < "$BREAKDOWN" | tr -d ' ')
[ "$BFIELDS" -ge 10 ] || fail "拆解笔记只有 $BFIELDS 个字段标题（需 10），疑似没逐字段填"
[ "$BSIZE" -ge 8000 ] || fail "拆解笔记只有 $BSIZE 字节（需 8000），拆得太浅"

# ---------- 实现级闸（2026-09-14 加）----------
#
# 标定依据（拿三份真实拆解笔记回测，不是拍脑袋）：
#   笔记                                 含具体数字的行   字节    实际产出
#   2026-09-13 agent-shells（三项目拼盘）        76       32270   9910 汉字 ≈58 分钟  ← 好
#   2026-09-11 AutoGPT（单项目）                 32       14689   5366 汉字 ≈31 分钟  ← 尚可
#   2026-09-12 Codex（单主题）                    9        8530   3645 汉字 ≈21 分钟  ← 差
# 裂缝在 9 与 32 之间，阈值取 20，两边都留余量。
#
# 被拿掉的一条（重要，别再加回来）：原本想卡「代价」出现 ≥3 次，回测发现三份笔记
# 「代价/成本/坏处/负担/放弃/牺牲/取舍」合计都是 2 次——完全不区分好坏。项目记忆里
# 早写过「试过用稿子里出现多少文件名当指标，四期真稿子全过不了线，量错了东西」。
# **给闸门加指标之前，先拿正负样本各测一遍。没测过的关键词一律不进硬闸。**
#
# 三节（二次深读 / 取证台账 / 取舍台账）的处理：
# 硬闸只要求「至少有一节」——好样本 rev.2 只有 `## 13. 取证台账`，没有 `## 二次深读`，
# 硬卡三节会把它判死。逐节缺失只提示，不拦。等新流程跑出两期正样本，再考虑升成硬闸。
DEEP=0
for sec in 二次深读 取证台账 取舍台账; do
    if grep -qE "^##+ *([0-9]+[ .、]+)?${sec}" "$BREAKDOWN"; then
        DEEP=$((DEEP + 1))
    else
        echo "[!] 提示：拆解笔记缺「## ${sec}」一节（prompt 要求有，见 skill podcast-depth-writing）" >&2
    fi
done
[ "$DEEP" -ge 1 ] || fail "拆解笔记里「二次深读 / 取证台账 / 取舍台账」三节一节都没有——没有实现级内容"

VALUEN=$(grep -cE '[0-9]{2,}' "$BREAKDOWN")
[ "$VALUEN" -ge 20 ] || fail "拆解笔记只有 $VALUEN 行含具体数字（需 ≥20，好样本 76 / 差样本 9）——供料还是架构级"

# 时效闸：只拦真缺项，不判内容质量。
grep -qE '信息截止[:：]' "$SCRIPT" || fail "稿子开头没写「信息截止：YYYY-MM-DD」"
grep -qE '信息截止' "$BREAKDOWN" || fail "拆解笔记缺「信息截止」栏"
grep -qE '当前版本' "$BREAKDOWN" || fail "拆解笔记缺「当前版本」栏"

# 黑名单闸（2026-09-14 加）：把「写在文档里的规则」变成「代码拦得住的规则」。
# 已被官方继任/停服的项目不许当成本期主角。只看稿子**开头**（标题 + 前 8 行）——
# 讲现役拆解的话，项目名一定出现在这里；正文里顺带提到它做对比是允许的。
# 拆解笔记不查这条（附录留档是被鼓励的做法）。
#
# 2026-09-21 修 bug：原来直接把整行当匹配串读进来，而每行行尾都有 `\t# 官方口径…`
# 注释，于是 grep -F 拿「gitleaks\t# README 顶部…」这种整串去找，永远匹配不到——
# 这条闸从 09-14 立起来到 09-21 之间**一次都没真正拦过**（拿 Gemini CLI 当正样本
# 实测确认）。现在先剥行尾注释再匹配。改这里之后必须重跑正负样本：
#   正样本：head 里有「Gemini CLI」或「gitleaks」→ 必须判 FAILED
#   负样本：head 里只有当期项目名 → 必须放行
if [ -f "$BLACKLIST" ]; then
    HEAD8=$(head -8 "$SCRIPT")
    while IFS= read -r line; do
        line="${line%%#*}"
        line="$(printf '%s' "$line" | sed 's/[[:space:]]*$//')"
        [ -z "$line" ] && continue
        if printf '%s' "$HEAD8" | grep -qiF -- "$line"; then
            fail "稿子开头出现黑名单项目「${line}」（已被取代或停服，不许做现役拆解）"
        fi
    done < "$BLACKLIST"
fi

# ---------- B 时长闸：写没写够 ----------

HAN=$(python3 -c "
import re, sys
t = open(sys.argv[1], encoding='utf-8').read()
print(len(re.findall(r'[一-鿿]', t)))
" "$SCRIPT")

DETAIL=$(grep -oE '[A-Za-z0-9_.-]+\.(py|js|mjs|ts|tsx|go|rs|md|json|ya?ml|toml|sh|css|html|txt)' "$SCRIPT" \
    | sort -u | wc -l | tr -d ' ')

PROJ=$(head -1 "$BREAKDOWN" | sed 's/^# *拆解笔记 *[·:：] *//')
[ -n "$PROJ" ] || PROJ="未登记"

read -r EST <<<"$(python3 -c "h=$HAN; print(f'{h/175:.0f}')")"

echo "汉字 $HAN ｜ 具体值 $VALUEN 行 ｜ 实现级节 $DEEP/3 ｜ 文件名 $DETAIL 处"
echo "拆解笔记 ${BFIELDS} 字段 / ${BSIZE} 字节 ｜ 项目 $PROJ"
echo "预估音频 ${EST} 分钟 ｜ 目标 8500-10500 汉字（≈49-60 分钟）"

# 两档：<6500 判失败（明显没写够）；6500-8500 放行但标 SHORT。
# 两档是为了不出现「一夜没稿可听」——那比短更糟。
SHORT=""
if [ "$HAN" -lt 6500 ]; then
    fail "只有 $HAN 汉字（<6500，≈$EST 分钟），远低于一期正常量，拆得太浅"
fi
if [ "$HAN" -lt 8500 ]; then
    SHORT=" | SHORT 偏短（目标 8500-10500）"
    echo "[!] 汉字 $HAN < 8500（≈49 分钟），放行但标 SHORT"
fi

printf 'OK %s %s | %s汉字 | 拆解%s字段 | 预估%s分钟%s\n' \
    "$TODAY" "$PROJ" "$HAN" "$BFIELDS" "$EST" "$SHORT" > "$STATUS"
echo "[✓] 验收通过，状态已落 $STATUS"

# ---------- C 讲稿推飞书（2026-09-16 加）----------
#
# 过闸之后把讲稿 md 推成飞书选题表当天排期记录的「稿子」附件。
# 刻意不动 latest-status.txt：02:00 合成班读的是它首行 OK 的契约，推送结果不该混进去。
# 推送失败**不影响验收结果**——稿子本身已经验过了，这一步是锦上添花，不是闸门。
printf '\n--- %s push-script %s ---\n' "$(date '+%F %T')" "$TODAY" >> output/feishu-push.log
if python3 scripts/feishu_sync.py --push-script --date "$TODAY" >> output/feishu-push.log 2>&1; then
    echo "[✓] 讲稿已推飞书"
else
    echo "[!] 讲稿推飞书失败，详见 output/feishu-push.log（不影响验收结果）" >&2
fi
