# BLOCKED.md（待裁决清单）

## 2026-10-03 夸克备份链路（本轮 /goal，最新在最上）

1. **【已解决】夸克登录态（原「拿不到 Cookie」阻塞）**
   2026-10-03 22:51 解决，方式是**浏览器扫码驱动**而非手抄 Cookie：
   - playwright（本机已装，无新增安装）开无头 Chromium 打开 `pan.quark.cn`，截图二维码给用户，用户用夸克 APP 扫；
   - 脚本轮询到 `__pus` cookie 后用 `context.cookies()` 抓全量（含 HttpOnly），经 stdin 直接喂给 `bash scripts/upload-quark.sh --set-cookie`，**全程不打印、不落盘**；
   - `--set-cookie` 自带的 `kuake user` 验证通过（Keychain 服务名同脚本内 KEYCHAIN_SERVICE）。
   补传随即完成：10-01/02/03 三个 m4a 均 `bin/kuake list "/"` 在列，`output/upload-quark.log` 三行 OK。
   ⇒ **下次 Cookie 失效照此办理即可，不必再等用户手抄**；要点已写进 `docs/夸克备份.md`。

2. **飞书告警通道本身是坏的（`agent.notify` → lark-cli 缺 scope）**
   证据：`python3 -m agent.notify --text ...` → `{"ok": false, "identity": "user", "error": {"type": "authorization", "subtype": "missing_scope", "message": "missing required scope(s): im:message.send_as_user", "hint": "run \`lark-cli auth login --scope \"im:message.send_as_user\"\` ..."}}`。
   影响：夸克上传失败时该推的告警推不出去（脚本按设计兜底：只打本地提示，不崩、不阻断）。网易云那侧同样收不到。
   修法（用户手动，要浏览器授权，本执行者白名单外没动）：`lark-cli auth login --scope "im:message.send_as_user"`。

3. **顺手记的三条（不阻塞）**
   - `output/upload-quark.log` 里 2026-10-03 22:35 那条 `template-... FAIL` 是反向验证用占位 Cookie 触发的测试行，不是真上传事故。
   - `bin/kuake` 是 darwin-amd64 二进制，M4 靠 Rosetta 跑，实测正常；以后若换官方 arm64 版，`docs/夸克备份.md` 的重下命令和字节数要同步改。
   - 夸克 Cookie 现已配置（22:51 起）；夸克登录态会过期，失效现象与代抓办法见 `docs/夸克备份.md`，届时按该文档「懒人办法」节重走一遍扫码即可。
   - 网易云 CLI 已由用户扫码登录成功（22:51:41，账号 fdxffdcc）；凌晨的自动重登按原机制自行刷新，无需干预。

---

> **2026-09-21 洁癖收尾的现状标注**：本文件里下面这些已经**毕业进 `CLAUDE.md`，不再是待裁决项**，
> 原文保留只作轨迹：
> - 「顶部」第 1/3 条（死代理 127.0.0.1:7890）→ 已是 `CLAUDE.md`「环境陷阱」第 1 条（用 `env -u` 绕行）
> - 「顶部」第 2 条（`DOUBAO_TTS_KEY` 为空）→ 已是红线：Key 只从环境变量读、不落文件；且豆包 seed-audio 路线已不需要它
> - 「顺手发现」第 1 条（`fetch.py` 吞错）→ 已是 `CLAUDE.md`「环境陷阱」第 2 条
> - 「顺手发现」第 2 条（库里没有 push 字段）→ 已是 `CLAUDE.md`「技术栈」里那句「由 episode.py 调 GitHub API 实查」
> - 2026-09-11 夜 第 5 条（`AGENTS.md`/`CLAUDE.md` 双份真相）→ 已解决，见该条自己的记录
>
> **仍然开着的**：2026-09-11 夜 第 1/2/3/4 条（TTS 参数调优、上传网易云、待注册本地系统、重复 skill）。
> **新增待裁决见文件末尾「2026-09-21」一节**。

## 顶部：任务 0 与任务书不符项

1. **代理 127.0.0.1:7890 已死**（任务 0.3 未过）
   证据：`https_proxy=http://127.0.0.1:7890 git ls-remote ...` → `Failed to connect to 127.0.0.1 port 7890 ... Couldn't connect to server`；lsof 扫描无任何进程监听 7890/7891/1087/8889 等常见代理端口；本机装有 Clash Verge.app / FlClash.app 但均未运行。
   处置：GitHub / aihot / TTS 全部改直连（已验证 git ls-remote 与 fetch.py 直连可用）。待裁决：是否需要开机常驻 Clash（涉及系统配置，未动）。

2. **DOUBAO_TTS_KEY 环境变量为空**（任务 0.4 未过）
   证据：`[ -n "$DOUBAO_TTS_KEY" ]` → 空。
   处置：任务书末尾附了 key，任务 3 不缓做；以命令行内联 `DOUBAO_TTS_KEY=*** python3 scripts/tts.py` 方式注入（key 不写入任何文件/日志，符合红线）。待裁决：若希望长期用，需自行把 key 放进 shell profile（我不代写，避免 key 落文件）。

3. **shell 环境全局代理变量指向死代理**（http_proxy/https_proxy/HTTP_PROXY/HTTPS_PROXY=127.0.0.1:7890）
   影响：任何继承该环境的网络程序默认全挂。fetch.py 首次裸跑因此把 output/2026-09-09.md 覆盖成 107 字节空壳（详见 PROGRESS.md 决策记录）。处置：所有命令用 `env -u ...` 或 `--noproxy` 规避。待裁决：环境变量从哪里注入的（zshrc？Trae？）需领导自查。

## 顺手发现、未动手的 bug（按界限只记录）
- fetch.py 所有查询失败时仍退出码 0（吞错），且仍会覆写当日 md → 已实际造成数据覆盖事故一次。建议 v2 修：查询全失败时拒写 md / 退出码非 0。
- info_source.db 无 push_at / updated_at 字段，任务 1 的「近 90 天有 push」无法从库内判断，episode.py 改用 GitHub API 实时查询该字段。
- ✅ **已结（2026-09-10 洁癖收尾）**：`任务书-播客第一期.md` 里的明文 API key。
  - **先更正旧记录**：本条原先写「任务书.md 含明文 key」并断言「任务书-播客第一期.md …未见 key 本体」——**两句都不对**。项目内没有叫 `任务书.md` 的文件，而 `任务书-播客第一期.md` 第 43 行 key 就在那儿。原文那个「未见」会让后来人以为不用查，属安全相关的假阴性。
  - **处置**：明文**已抹除**，替换成一行说明。领导 2026-09-10 确认这条火山 seed-tts-2.0 API 路线**暂时不用**（现走豆包 seed-audio），所以不做轮换。
  - 抹前实测：该 key 在本机是**独苗**（全局 shell 配置里没有同一条，`$DOUBAO_TTS_KEY` 也是空的）。
  - 任务书本体已挪到 `_归档/项目根/`，全貌见 `_归档/README.md`。
  - 另：本机全局配置里也发现有明文 key，与本项目无关，未动。**教训与本案同源：key 抹掉之后要去控制台轮换，不要留着「反正没人知道」。**

## 其他待裁决
- ~~✅ 已裁决（2026-09-10）：语速 vs 时长冲突 → **语速优先，时长不设目标值**。atempo 0.72 是为了听着舒服（340→~230 字/分），不是为凑 45 分钟。任务书里「mp3 ≥45 分钟」「字数 10000-13000」这类固定值全部作废，改弹性判据。~~
  - ⚠️ **2026-09-21 更正：这条已被推翻，别再照它办。** 2026-09-13 用户反馈「一路滑到 23 分钟、拆得太浅」，
    于是**时长回到闸门**：正文汉字硬门 8500（≈51 分钟）、<6500 判失败、6500-8500 放行但标 `SHORT`。
    现役判据以 `CLAUDE.md`「验收口径」表 + `scripts/verify-episode.sh` 为准。
    （保留原文是因为它解释过 2026-09-10 那轮「撤掉固定值」的来由；但**结论已作废**。）

## 2026-09-11 夜 · 待裁决（本地语音链路完善那轮的收尾）

1. **Task 4 质量参数调优**（`cfg_value` / `inference_timesteps` / `temperature` 三组 A/B）：没做——需要你的耳朵 + 独占 TTS 服务，属可选。要做就在整期跑完后单独开一轮。
2. **上传网易云（C1）**：等整期本地成品出来 + 音色定稿再传（`bash scripts/pipeline.sh upload-local <m4a>`）。本地产物带 `-local` 后缀，跟豆包版不撞名。注意 `ncm-cli` 装在 `~/.npm-global/bin`，定时任务环境里要显式 `export PATH="$HOME/.npm-global/bin:$PATH"`。
3. **A 类本地系统只挑出 1 个待注册**：`~/ai-brain/xiaoetong-downloader-v2/`（小鹅通课程下载器，入口 `python3 web_server.py`）。注册只写 SKILL.md、不搬 2.7G 目录。要不要注册等你一句话；清单见 `ai-jarvis/references/local-capabilities.md`。
4. **重复 skill**：`~/.hermes/skills/media/local-audio-transcription`（Hermes 私有）与主库的 `sensevoice-onnx` 同主题重复，建议并进后者后删掉前者的本地入口，或改成一行指针。未动，等你确认。
5. ~~**`AGENTS.md` 与 `CLAUDE.md` 双份真相**~~ —— **2026-09-15 已解决，不再是待裁决项**。
   用户拍板「统一到 Claude」（他主要用 Claude Code），现为 `AGENTS.md` → `CLAUDE.md` 软链，**`CLAUDE.md` 是唯一真身**（11569B，两级 `shasum` 一致）。
   病根经过两次：2026-09-11 发现 CLAUDE.md 的「语速定档」停在旧档 PACE 3.58；2026-09-15 洁癖收尾又发现它落后到 09-13、写着「豆包班已关 / WorkBuddy 已弃用」等已被推翻的流水线口径——而 Claude Code 读的正是它。
   原建议是反向软链（`AGENTS.md` 当真身），按用户「主要使用 Claude」的实际用法改成了 `CLAUDE.md` 当真身。

无其他阻塞。

---

## 2026-09-21 夜 · 待裁决（洁癖收尾那轮新增）

1. **要不要把本地兜底开回来**（原来是「哪条定时任务该关该改」，Trae 侧已澄清、这一半解决了）：
   用户 2026-09-21 确认 **Trae 侧没挂任何任务**。WorkBuddy 面板实测 →「播客本地兜底」03:00 **PAUSED**、
   「选题库周排期」周日 05:00 ACTIVE、「播客提醒」06:30 ACTIVE、写稿 00:34 ACTIVE。
   于是**兜底完全空缺**：豆包那班失败就没人救（ep15 缺音频即为此）；调研稿链路也没有调度。
   → 要么在面板里打开 03:00 那条，要么装 `agent/launchd/` 的新兜底班（它按 mtime 判成品，
   绕开了旧脚本「文件名带日期」那个永远不成立的判据）。**开关只能在面板里动手。**
2. **语速换算三处口径不一致**（老问题，第九次提出）：`write-episode-prompt.md` §0.5 说汇报按 **170–185**、
   141 作废；`CLAUDE.md`「验收口径」与 `verify-episode.sh` 仍 `÷168`，脚本还多印「1.5x 收听」
   （而 `CLAUDE.md` 明说 1.5x 汇报已去除）；新的 `config/agent.json` 也取 168。
   → 你定一个数，我改 config + 那两处。
   - ✅ **已裁决（2026-10-03）：统一 175 汉字/分**——豆包 seed-audio 六样本实测散布 140-195 的中位偏保守值。
     已改 12 个文件：`config/agent.json`（chars_per_minute）、`scripts/verify-episode.sh`（÷175、status 行去掉
     「1.5x 听」尾巴）、`scripts/write-episode-prompt.md`、`agent/request.py`、`CLAUDE.md`、`README.md`、
     `定时任务.md`、`DESIGN.md`、`docs/全流程梳理.md`、`docs/seed-audio-schedule.md`、
     `scripts/research-synth.sh`、`docs/播客Agent架构设计.md`。**闸门硬阈值 8500/6500 一个字没动**；
     产出侧 PACE 4.0 ≈187 是合成档位，明确不互改。口径守卫 = `tests/test_speed_caliber.py`
     （`python3 -m unittest discover -v`，STALE 模式扫上面 12 个文件）。
     上文保留原叙述——它是这条漂移史 itself，删了下次还会犯。
3. **ep15 的音频要手动补**：09-21 那期稿子 08:40 才落盘（白天），豆包那班的「12 小时」闸已过期，
   不会自动合成 → `bash scripts/pipeline.sh synth-local`，或先 `touch output/latest-script.md` 再触发豆包那班。
4. **agent 外环要不要挂定时**（设计稿第 6 步）：先跑通一期真稿再拆旧，前提在 `agent/launchd/README.md`。
5. **工作区残留（未确认前一个都没删）**：`PROGRESS.md`（2026-09-10 的一次性进度记录，已被
   `README.md` + 记忆取代）、`p1b-selection.png`、`tts-console-free-default.png`、`volc-agent-page.txt`
   （三者在全仓零引用）、`info_source.db.backup-20260914-2028`（DB 备份，`*.db.*` 已被 gitignore）。
