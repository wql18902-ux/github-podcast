# PROGRESS

## 目标 / 顺序 / 最大风险（任务 0 结论）
- 目标：一期 50 分钟播客 mp3 落盘 output/audio/，文稿 ≥10000 字，听得懂 > 做得全 > 做得快
- 顺序：任务 1 选料（episode.py → brief）→ 任务 2 写稿 → 任务 3 TTS 合成 → 验收
- 最大风险：代理 127.0.0.1:7890 已死（环境变量+git 全局配置都指向它），全部网络操作改直连；TTS 真实效果待听

## 任务 0 核对（2026-09-09）
1. aihot API ✓ 直连 200，items 非空（须绕过死代理 env）
2. fetch.py ✓ 退出码 0（须 `env -u http_proxy -u https_proxy ...` 跑；首次裸跑被死代理拖垮、覆盖了当日 md，已无代理重跑恢复：120 入库 / 86 海外）
3. 代理 git ls-remote ✗ 7890 无进程监听；GitHub 直连可用（`git -c http.proxy= -c https.proxy=`），clone 改走直连
4. DOUBAO_TTS_KEY 环境变量为空 → 已记 BLOCKED.md；key 由任务书提供，运行时以 `DOUBAO_TTS_KEY=... python3 scripts/tts.py` 内联注入，不落任何文件

## 进度
- [x] 任务 0 环境核对 + PROGRESS/BLOCKED 建立
- [x] 任务 1 scripts/episode.py 选料 → output/2026-09-09-brief.md（项目 affaan-m/ECC ⭐254k，Agent/LLM 主线；新闻 5 条人工配平：Navier-Stokes 合并 1 条 + Dwarkesh 数据研究 + Images 2.5 + Mistral 融资 + CUA-Lite；ECC 已入 episodes.log）
- [x] 任务 2 文稿 → `output/episodes/ep2-ecc/`（11705 字含标点，口径照 podcast-01：口语/类比/判断标准；该目录下有三版：`script.md` / `完整稿-50min.md` / `试水稿.md`）
- [x] 任务 3 scripts/tts.py → output/audio/2026-09-09-ep2.mp3 ✅（123 段全部成功，16.6MB→atempo 后 23MB，24000Hz 单声道 64kbps）（2026-09-10 归入 `_归档/`——同期已有更好的 seed-audio 版 `ecc-播客完整版-51min.m4a`）
  - 反向验证红→绿：错 key → HTTP 401 ×3 重试后退出码 1 ✅；真 key → 样例与全量均成功 ✅
  - 实测 TTS 语速 ~340 字/分钟（远快于任务书假设的 220）→ API speed 参数无效、两音色语速相同 → ffmpeg atempo=0.72 后处理（保音高变速），最终语速 ~232 字/分钟
- [x] 终验全部通过：
  - afinfo 时长 3021.456 秒 = 50.36 分钟 ≥45 ✅
  - 文稿 11705 字（含标点；11705/50.36min ≈ 232 字/分钟，与任务书 220 字/分钟口径自洽）✅
  - episodes.log = [ggml-org/whisper.cpp, affaan-m/ECC]，本期项目非 whisper.cpp ✅
  - fetch.py 重跑退出码 0（120 入库/86 海外）✅
  - grep 'X-Api-Key'：我方代码仅 scripts/tts.py 读环境变量行 ✅（任务书.md 明文 key 系用户自写，已记 BLOCKED.md 待裁决）

## 状态：第 2 期交付完成（2026-09-09）

## 后续期次（补记）

### 第 3 期 · hermes-agent（2026-09-09 夜）
- [x] 选料 NousResearch/hermes-agent，clone 至 cache/hermes-agent
- [x] 文稿 `output/episodes/ep3-hermes-agent/script.md`：20069 汉字，质检硬失败项全清
- [x] 音频 `output/audio/hermes-播客完整版-114min.m4a`：55.7MB
- [x] 已入 episodes.log

### 第 4 期 · n8n（2026-09-10 凌晨，交付完成）
- [x] 选料 n8n-io/n8n，clone 至 cache/n8n（episode.py clone 超时中断，episodes.log 未自动追加 → 手工补录）
- [x] 文稿 `output/episodes/ep4-n8n/script.md`：9033 汉字（当时代号为 `latest-script.md`，后被第 5 期覆盖，2026-09-10 归档改现名）
  - 首版 4720 字未达标 → 重写扩写；质检清 2 处硬性翻案句 + 7 处翻案腔变形 + 模型腔软标记，failures 清零
- [x] 音频 `output/audio/n8n-播客完整版-60min.m4a`：afinfo 3600.0 秒 = 60.00 分钟（下限 30 分钟 ✅，长短随素材不设目标值），29.3MB
- [x] episodes.log = [whisper.cpp, ECC, hermes-agent, n8n-io/n8n]，本期项目未重复 ✅

### 第 4 期遗留（2026-09-10 全部结掉）
1. ~~稿件未用任务书规范名~~ → `latest-script.md` 已成为**约定固定路径**（豆包读它），同时留 dated 副本 `output/<日期>-script.md`
2. ~~音频为 m4a，任务书要求 mp3~~ → m4a 是 seed-audio 主路线的格式，mp3 那条是旧 API 备选路线
3. ~~质检剩破折号/冒号未结~~ → DESIGN.md 5.2 定死保留（口播停顿信号，TTS 会读成停顿），与 human-writing 原版的分歧是有意的

### 第 5 期 · Claude Code 标本（2026-09-10 15:15 写好稿，音频待合成）
- [x] 拆解笔记 `output/2026-09-11-breakdown.md`：10 字段 / 9504 字节（**新过程闸的第一份真稿，实测通过**）
- [x] 文稿 `output/2026-09-11-script.md` + `latest-script.md`：9636 汉字（新判据：不设下限不设上限）
- [x] episodes.log 已记 `topic:AI-Agents(Claude-Code)`（**条目格式不规范**，记的是主题串不是仓库名；只追加不删改的规矩在先，未动）
- [ ] 音频未合成 → 待豆包 02:00 那班跑
- 状态文件 `output/latest-status.txt` 是**旧格式**（`OK 2026-09-11 topic:... 9636字`，没有 `| 拆解N字段 | 预估X分钟/1.5x听Y分钟` 那段）——它是新 `daily-prepare.sh` 上线前写的，下次由脚本覆盖成新格式

## 在飞的东西（暂停，没做完）

### 本地 TTS 选型调研（2026-09-10 19:17 起，停在 Phase 0）
- 工作区：`research-2026-09-10/`（项目根目录，deep-research skill 的按日工作区）
- 进它先读 `research-2026-09-10/handoff.md`——那里面有当前 Phase、已确认事实、下一步、未解决风险
- 目的：找一条**不依赖豆包云端**的本地 TTS 路线，接进现有流水线
- 现状：7 个文件里 6 个还是骨架（`truth-source/*` 写着「待 Phase 3 填充」），**没有出过任何结论**
- 卡在哪：16GB 内存跑不跑得动重模型没实测；本地音质 vs 豆包 seed-tts-2.0 差距未知（E001-E007 已登记在 `evidence-ledger.md`）
- 为什么停：当晚转去做套1 定时任务改造。**不是废弃，随时可续**——续的时候从头读 handoff.md 即可

## 决策记录
- **套1 载体再改：launchd → fanbox 定时任务（2026-09-10 晚）**：领导提出他基本一直开着 FanBox，用它的定时任务更好查看管理（带最近 10 次成功/失败/错过历史）。我原先主张 launchd 的那个「唤醒后补跑」优势被推翻——补跑发生在豆包 02:00 过闸之后，豆包不会补合成，第二天早上一样没新一期；硬要求只是「机器 22:30 醒着」，两者相同。换过去还白得真终端（吃登录 shell 的 PATH，没有 launchd 那个 PATH 陷阱）。
  - 落地两条：`播客夜班写稿`（shell / 每天 22:30 / `bash .../daily-prepare.sh`，不勾全自动）+ `选题库周排期`（claude / 每周日 21:00 / 勾全自动）。
  - **为什么是两条**：fanbox 一条任务只能有一个「谁来干」+ 一个「什么时候」，这两件事两项都不同，塞不进一条。两条在同一列表里。
  - **怎么建的**：界面填表连错两次（把说明文字当内容填了），最后走 HTTP API `POST localhost:4567/api/cron/save` 直接建（`server.js:2505`，与界面同一套实现，不重启、不覆盖内存态）。
  - plist 保留在磁盘、已 bootout 作备用。**装回来前必须先停 fanbox 那条**，否则 22:30 双跑打架。
- **改自动流水线 + 弃用 WorkBuddy（2026-09-10 领导拍板，覆盖同日上午那版）**：
  - 套1 写稿从 WorkBuddy 换成本机 launchd（`com.github-podcast.prepare`），时间 00:00 → **22:30**（写稿要 1-3h，得给豆包 02:00 留窗口）。WorkBuddy 定时任务已删（`deleted_at=2026-09-10 18:19:21`，最后一次 00:00 跑失败：`Conversation ended before automation request completed`）。
  - **字数下限也取消了**。上午那版留了「≥9000 起步」，实测正是它逼出凑字：`首版 4720 字未达标 → 重写扩写`。改成不设下限不设上限，撑不起就同主题拼盘（最多 3 个项目，各走完整 10 字段），真判据换成信息密度（≥8 处具体的东西）。
  - **验收闸换代**：稿子 mtime 必须变新（拦「没写/没落盘」）+ 拆解笔记 ≥10 字段标题且 ≥2000 字节（拦「跳过读源码」）。试过用「稿子里出现多少文件名」当指标——四期真稿子全过不了线，口语稿天然说「它的记忆模块」不说 `memory.py`，量错了东西，弃用。**别再往这个方向加指标。**
  - **失败不再静默**：无论成败都写 `output/latest-status.txt`，豆包读到非 OK 就跳过。之前是失败不覆盖 → 豆包把上一期重新合成一遍，人听不出来还以为是新的。
  - **待消费闸**：`latest-script.md` 比 `output/audio/` 最新成品还新 → 本轮跳过不覆盖（带 48h 逃生门）。防的是「稿子写好了还没合成，被下一轮盖掉，那期永远出不来音频」。已实测三种情形（待消费→拦、已合成→放行、上期本就失败→放行）。
  - **语速定档**：产出侧不动（~148 汉字/分，正是 `split_segments.py --unit char` / PACE 3.58 那档），他 1.5x 听 → 222 汉字/分，落在标准播客速区间。旧的「提到 220 汉字/分」待办作废（那是按 1.0x 算的，真开 1.5x 会到 330）。按倍速调的是内容不是语速：开头 100 字进正题、语气词 ≤3/千字、同一观点只讲一次。
  - **选题入口换文件**：新建项目根目录 `选题库.md`（困惑清单 / 本周主题 / 想听的 / 排期），取代 `output/选题提示.md`（先转废止指针，2026-09-10 洁癖收尾挪进 `_归档/`）。
- **验收不写死固定值（2026-09-10 上午拍板，其中字数一条已被上面那版覆盖）**：「50 分钟 / 45 分钟 / 10000-13000 字」这类固定值把手段当目标——为凑时长而拖慢语速、为凑字数而注水。全项目改弹性判据：字数 ≥9000 起步不设上限、时长 ≥30 分钟硬拦 + 30-45 分钟只提示、语速 ~230 字/分为「听着舒服」而非凑时长、防作弊改用「项目未入 episodes.log + 稿件有源码级细节」。已同步改 CLAUDE.md（新增验收口径表）、scripts/pipeline.sh（MIN_SEC/SOFT_SEC 可用环境变量覆盖）、README.md、DESIGN.md、docs/tts-flow.md、定时任务.md、write-episode-prompt.md。任务书本体 2026-09-10 归档至 `_归档/项目根/`。
- 代理死 → 所有外网请求直连（fetch 重跑已验证、git ls-remote 已验证），原因见 BLOCKED.md
- fetch.py 首次裸跑把 output/2026-09-09.md 覆盖成空壳（107 字节）→ 无代理重跑恢复 221 行，未动 fetch.py 本体
