# github-podcast 规则

> 本文件只管**本项目**规则。全局身份/偏好/红线不在这里——那些在你自己的 AI 工作站里。
> 新会话开工先读本文件 → `README.md` → `config/audience.md`（听众画像，改口径的入口）。

「AI 前沿个人播客」流水线（时长随素材，不设固定值）：`fetch.py` 信息源 → `scripts/episode.py` 选料
→ 夜班拆解写稿 → 自动合成（本地 VoxCPM2，`scripts/tts_local.py`）→ 网易云云盘收听。

## 必守红线

- **API Key 只从环境变量读**，不写进任何文件/日志/输出。云 TTS 控制台的 Key 只进 Keychain，
  不落项目文件、不写日志、不回显到页面。
- **`fetch.py` 的 `QUERIES` 和 `KNOWN_CN_ORGS` 不许动**，只在外围加文件。要换关注方向见 README「定制化」。
- **删除只进废纸篓，不 `rm -rf`。**
- **`output/episodes.log` 是防重复讲过的记录，只追加不删改。**
- **`output/latest-status.txt` 只由 `scripts/verify-episode.sh` 写。** 写稿 agent 碰它就是污染闸门。
- **文稿口径照 `samples/ep1-whisper-cpp/script-样板.md`**：中文口语、讲给「你」听、概念配生活类比、
  结尾给一条判断标准。讲透为止，不设字数目标（但验收闸有硬门，见下）。
- **`config/audience.md` 不进库**（`.gitignore` 挡着）。进库的只有 `audience.example.md` 模板。

## 听众画像是单一真相源

「讲给谁听、他的现实约束、类比从哪里取、什么话题避开」只在 `config/audience.md`。
选稿 prompt、写稿 prompt、审稿 prompt 全部从那里取（走 `scripts/audience.py`）。
**不许在任何一个 prompt 里写死个人信息**——写死了就是「换听众要改八个地方」。

## 双链写法

- 期次互指 `[[ep<N>-<slug>]]`；产品/公司地图 `[[agent-map]]`；笔记/稿子用文件名
- 纯文本双括号，**不搬家、不建库、不装插件**。用 Obsidian 打开本项目时自动成网；不用它也不影响任何脚本
- 每期 `page.md` 至少 2 条出链；新写的稿子和拆解笔记，结尾加一节 `## 相关` 列出双链
- 常驻地图 `agent-map.md` 是单一真相源：产品换代只改这一处，旧稿不动（红线：只追加）

## 验收口径

时长回到闸门（2026-09-13 起，此前「不设目标值」一路滑到 23 分钟、拆得太浅），
换算锚在实测上：**正文汉字 ÷ 168 ≈ 音频分钟**。

| 项 | 判据 | 说明 |
|---|---|---|
| 稿子被更新 | `latest-script.md` mtime 变新 | 拦「agent 没写 / 写了没落盘」 |
| 够时长 | 正文汉字 ≥8500（≈51 分钟） | <6500 判失败；6500-8500 通过但标 `SHORT` |
| 密度跟得上 | 每 1000 汉字 ≥2 处具体的东西 | 防「长而水」。写在 prompt 里，脚本只报数不判死 |
| 过程走了 | breakdown ≥10 字段标题 + ≥8000 字节 + 含具体数字的行 ≥20 | 拦跳过读源码。**「读没读源码」唯一能机械验的证据** |
| 防重复 | 本期项目不在 `episodes.log` 出现过；不在 `scripts/blacklist-projects.txt` | 拦重讲旧项目 |
| 失败不静默 | 无论成败都写 `latest-status.txt` | 合成链路读到非 OK 就跳过，不会把旧稿重录一遍 |

> 试过用「稿子里出现多少文件名」当机械指标，四期真稿子**全过不了线**——口语稿天然说
> 「它的记忆模块」而不是 `memory.py`。量错了东西，已弃用。别再往这个方向加指标。

> **动 `verify-episode.sh` 的黑名单闸之后，必须重跑正负样本**：拿 Gemini CLI / gitleaks 当正样本
> 必须判 FAILED，现役项目必须放行。2026-09-21 之前那个 bug 立起来 7 天一次都没拦过——
> 整行（含行尾注释）当匹配串，`grep -F` 永远匹配不到；而且 `fail` 那行的全角括号紧跟变量名，
> `set -u` 下必崩，两个 bug 互相掩盖。

## 语速定档

**产出侧 PACE 4.0**（`scripts/split_segments.py`）：单段 450-500 字 ≈ 120s，
约 4 字符/秒 ≈ 187 汉字/分钟，**1.0x 直接可听**。
**1.5x 不是偏好，是补偿**——早期 PACE 3.58（~148 字/分）太慢，用户被迫开 1.5x。旧档 3.58 已作废。

## 环境陷阱（必看）

1. **死代理**：shell 环境 `http_proxy/https_proxy` 指向 `127.0.0.1:7890`，代理进程常不在。
   联网命令报 `Connection refused` 时用
   `env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY <命令>` 直连；
   git 另加 `-c http.proxy= -c https.proxy=`。脚本内部已自行绕过。
2. **本机 `grep` 可能是 BSD 版、不认 `\|` 交替**：`grep "a\|b"` **静默零命中**，
   看着像「确实没有」，能把结论带偏。多关键词一律 `grep -E`。
3. **中文提示里变量名后紧跟全角字符一律加花括号**：`"… $VAR（…"` 会让 bash 把全角括号首字节
   吃进变量名，`set -u` 下直接崩。
4. **拉大仓先比 tarball**：`git clone --filter=blob:none` 在超大仓上会卡在 fetch。
   先用 codeload tarball 比一次；**tarball 也会被中途截断**，截断就换 git；
   大仓直接走「先树后抓」——Trees API 拿全树 → 挑 6-10 个贴题文件用 raw 逐文件抓。
   `curl` 调 GitHub API **必须加 `--http1.1`**，否则 exit 16 静默失败。
5. **`fetch.py` 吞错**：GitHub 查询全失败仍退出码 0 且覆写当日 md。跑完必须检查输出有无
   `[!] 查询失败`，全失败则当日 md 不可信，须重跑。

## Agent 外环（双环设计的另一半）

`agent/` 是外环：本机 Python，**只许标准库 + subprocess**（红线，`cli doctor` 会查）。
管调度/闸门/降级/记账。与内环（你的 AI 会话）的交界是文件契约：

```
外环写 agent/request.json → 会话读它、写稿、写 agent/done.json → 外环 python3 -m agent.cli resume
```

旧 `done.json` 会被 mtime 判掉，不会拿上一轮的回执当这一轮干完了。
状态在 `info_source.db` 的三张表（`episodes` / `episode_events` / `agent_runs`），
**产物真相源仍是文件**，库里只存指针与指标。`episode_events` 只追加。

常用：`python3 -m agent.cli` 的 `doctor`（自检）/ `status` / `report` / `run --dry-run` /
`resume` / `fallback`。兜底班 plist 在 `agent/launchd/`（**先读同目录 README 的三条前提再装**）。

## 每期流程

**自动**（默认 00:34 起跑，可手动 `bash scripts/daily-prepare.sh`）：

1. `PREP_ONLY=1 bash scripts/daily-prepare.sh` —— `fetch.py` 抓当日清单（全失败自动拦截）
   + 国内大厂源 + `scripts/episode.py` 选料 clone，**跑到选料就停**
2. agent 读 `scripts/write-episode-prompt.md` 全文执行（深度规范指向 `skills/podcast-depth-writing/SKILL.md`）
   → 逐文件读源码 → 写 `output/latest-script.md` + `output/<日期>-script.md` + `output/<日期>-breakdown.md`。
   主稿末尾附**「本周新闻」常驻节**（≈1500-1900 汉字，最近 7 天 AI 行业大新闻，
   对 `output/news-covered.md` 去重、讲完回写）
3. `bash scripts/verify-episode.sh` —— **验收闸唯一入口** → 写 `output/latest-status.txt`

然后合成：读 `latest-status.txt`（首行须 `OK`）与 `latest-script.md`（须 12 小时内更新），
过闸后走 local VoxCPM2 合成并上传网易云云盘。

**调研稿链路**：跟拆解稿并列的第二条稿源，走「联网调研」而非「读源码」。口径在
`scripts/write-research-prompt.md`，产物落 `output/research/`，合成入口 `bash scripts/research-synth.sh`。
两条链路互不干涉。

**目录约定**：`output/README.md` 写清哪些路径被脚本硬编码、历史期次怎么归档。改输出路径前先读它。
