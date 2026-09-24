# 播客 Agent Harness 架构设计

> 状态：设计稿 v1（待伟谦确认第 12 节的三个待拍项）
> 依据：现有流水线（`定时任务.md` / `scripts/` / `docs/seed-audio-schedule.md`）+ 用户 2026-09-21 确认的四条新约束
> 设计人：墨衡（agent-harness-architect）

---

## 0. 一句话

**任何 agent 当 harness，播客系统当应用。** 把现在散在 WorkBuddy / Trae / 豆包 / 手动四处的东西，收敛成「一个宿主自动化主班 + 一个本机 launchd 兜底班 + 豆包 App 作为外部合成执行器」，状态收进一张 SQLite 表，口径收进一份 JSON 配置，智能规范收进一份三家共用的 skill。

不是从零造 harness，是**给现成的 harness 装一个应用**，并把缺的那层（可续跑的执行循环）补上。

**宿主可换**：今天挂 WorkBuddy，明天想挂 Hermes 或 Claude Code，只改 ≤10 行的适配层，编排与 skill 一行不动。做法见 §3.1。

---

## 1. 需求规格

| 维度 | 内容 | 状态 |
|---|---|---|
| 目标与用途 | 每日自动产出一期讲给伟谦一个人听的播客，从抓源到上传网易云全程无人 | 已确认 |
| 成功标准 | 早上打开网易云云盘就有一期 51-62 分钟的音频；一夜没稿 = 失败；失败必须可见（不静默） | 已确认 |
| 任务结构 | 准备 → 读源码拆解 → 写稿 → 自验收 → **独立审稿** → 交豆包合成 → 超期降级本地合成 → 上传 → 推飞书 | 已确认 |
| 数据/资源边界 | 本机仓库与 `cache/`、GitHub API、`output/` 产物、SQLite、飞书多维表格、网易云云盘 | 已确认 |
| 硬约束 | ① 写稿模型固定 DeepSeek-V4.1-Flash，走 WorkBuddy 免费额度 ② 合成主走豆包 App（会员，省钱）③ 不把任何 Key 写进文件/日志 ④ 删除只进废纸篓 ⑤ 不改 `fetch.py` 的 `QUERIES`/`KNOWN_CN_ORGS`，不改 `episodes.log` 历史 | 已确认 |
| 用户与场景 | 一个人听，手机网易云；早间收听；一期 51-62 分钟 | 已确认 |
| 边界（不做什么） | 不做视频版；不自动换写稿模型；不在额度紧张时自动转付费合成；不动选题抓取规则 | 默认假设 |
| 技术栈约束 | **宿主无关**——WorkBuddy 优先，Claude Code / Codex / Hermes 都能驱动同一份流程；本机进程 = launchd；脚本保持 CLI 形态；状态进 SQLite；配置用 JSON（标准库零依赖） | 已确认 |

### 1.1 硬约束与向后兼容（最关键的一条）

**豆包那班的契约不能变。** 它靠两个文件干活，且是外部黑盒：

- `output/latest-status.txt` 第一行以 `OK` 开头
- `output/latest-script.md` 12 小时内更新过

新架构**必须继续产出这两个文件、格式一字不改**。任何「状态改存数据库就不写文件了」的想法都会直接掐死合成链路。这是本设计的第一条不可动约束。

---

## 2. 架构范式 P

| 子维度 | 决策 | 理由 |
|---|---|---|
| 扩展方式 | **薄适配 + 脚本即工具**（不是插件市场，也不是动态 function-calling 工具表） | 现有 28 个脚本全是 CLI，它们就是工具层。加能力 = 加一个脚本 + 在 `tools.json` 登记一行 |
| 配置方式 | **声明式 JSON**（`config/agent.json` 一份管全部口径） | 当前最痛的病根是「三处口径对不上」（22:00 vs 00:34、本地 vs 豆包谁是主路线）。判据、阈值、时间全收进一份文件，改行为改配置 |
| 部署拓扑 | **宿主无关的混合拓扑**：编排与状态在本机（任何 agent 可驱动），智能层由宿主提供，兜底跑 launchd，豆包独立在外部 | 免费额度随宿主走（三家共用 deepseek-flash）；本地 TTS 要吃 M4/Metal；豆包无 API 进不来；换宿主不重写 |
| 编排模式 | **显式状态机的固定管线**，不是自由 agent 编排 | 任务链是固定的（准备→写稿→验收→合成→上传）。checklist 明确警告过：「给固定管线配一个没人调用的工具注册表」是过度设计。只有「写稿」这一步内部才是 agent 自由循环 |

### 2.1 为什么是「双环」而不是「一个 agent 从头跑到尾」

这是本设计最核心的一个判断，先把反例摆出来（魔鬼代言人）：

> **反例**：把整条流水线塞进一个 WorkBuddy 会话，从抓源一路跑到上传。
> **它会在哪崩**：写稿要 2-4 小时。会话跑到一半被平台收走 / 超时 / 用户手滑关掉，**这一步的中间成果全部作废，无法续跑**——而且它不是「重跑一次就行」，是「已经读了 8 个源码文件的上下文全丢了，得从头再读一遍，积分双倍烧」。

所以拆成两环：

| 环 | 跑在哪 | 负责 | 特性 |
|---|---|---|---|
| **外环** | 本机 Python（`agent/pipeline.py`） | 调度、重试、断点续跑、闸门、降级、记账 | 确定性、可恢复、零模型成本 |
| **内环** | WorkBuddy 会话 | 读源码 → 写稿（自由循环，用免费额度） | 不确定性、只在这一步消耗模型 |

外环把「已经做完到哪一步」落进 SQLite，任何一环崩了，下一次从断点继续，**不重读已读过的文件**。

---

## 3. 技术栈选型

| 项 | 选型 | 理由 |
|---|---|---|
| 语言 | Python 3.9+（沿用现有 `python3`，不引入新运行时） | 现有脚本全是 Python + bash，零迁移 |
| Agent 运行时 | **WorkBuddy**（自动化 + 会话 + skill） | 免费额度、鉴权、工具循环、文件读写平台已提供，不重复造 |
| 调度 | 主班 = WorkBuddy 自动化；兜底班 = launchd（`com.github-podcast.fallback`） | 兜底是纯确定性脚本、零积分，不该占 WorkBuddy 自动任务名额，也不该依赖会话存活 |
| 状态 | SQLite，**复用 `info_source.db`**（新增 3 张表） | 单一真相源，且 `workbench_server.py` 已经在读这个库，期次状态可直接上页面，不用第二套 |
| 配置 | **JSON**（`config/agent.json` / `config/tools.json`） | 标准库 `json` 直接读，零依赖；与现有 `config/selection-sync.json` 风格一致。**刻意不用 YAML**——标准库没有 yaml，为一个配置文件引 pyyaml 不值 |
| 音视频 | `ffmpeg` / `afconvert` / `afinfo`（系统已有） | 现有链路原样 |
| 工具调用 | `subprocess` 调现有 CLI 脚本 | 工具层不动，只加一层注册与记账 |
| 外部 | `ncm-cli`（网易云）、`lark-cli`（飞书）、豆包 App（合成） | 现有 |

**明确不引入**：不装新 Python 包、不改 `fetch.py`、不重写现有脚本。新增代码只有 `agent/` 这一个目录。

---

## 3.1 跨宿主可移植（三层解耦）

> 用户诉求（2026-09-21 追加）：「我想要一个都是通用的，别的 Agent 也可以使用。」

**能做到，而且地基已经浇好了。** 实测事实（`ai-jarvis/references/三家Agent能力与分界线.md`，2026-09-12 实测快照）：

- `~/.claude/skills` 是**唯一一个 skill 库**，Codex / Hermes / WorkBuddy 全是指向它的软链
- 三家跑的是**同一个模型** `deepseek-flash`（都指向 `api.deepseek.com`）
- 三家**共用一份记忆** `~/ai-brain/ai-jarvis/memory/`
- 三家**不共享对话，只共享文件**——文件是唯一通道

所以缺的不是「通道」，是**流程与状态的归属**。现在流程藏在各家自动化里（Hermes 的 cron 目录、Claude 的 hooks、Codex 的 hooks.json、WorkBuddy 的 sqlite），那份文档的原话是「**改一处不会同步另一处**」。

### 解耦成三层

| 层 | 放在哪 | 换宿主时 |
|---|---|---|
| **编排 + 状态**（谁先谁后、记到哪、闸门判据） | 项目内 `agent/`（纯 Python + SQLite） | **不动**。任何 agent 跑 `python3 -m agent.cli run`，行为完全一致 |
| **智能规范**（写稿/审稿怎么写才算好） | `~/.claude/skills/podcast-agent/`（三家共用的软链库） | **不动**。三家加载的是同一份 |
| **宿主适配**（谁唤醒、用哪个模型、怎么给权限） | 各家的自动化配置，每家一份、每份 ≤10 行 | 只改这一层 |

### 各家怎么接（适配层全貌）

| 宿主 | 唤醒方式 | 模型 | 备注 |
|---|---|---|---|
| WorkBuddy | 自动化 | deepseek-v4.1-flash | 你现在的首选（免费额度） |
| Hermes | cron | deepseek-flash | 三家唯一有真定时的，适合「人不在电脑前」 |
| Claude Code | 手动 / hooks | deepseek-flash | **没有定时能力**，只能作手动补跑 |
| Codex | 手动 | deepseek-flash | 同上 |

**红线（可机械检查）**：`agent/` 目录**不许 import 任何平台 SDK**，只许标准库 + `subprocess`。这是「换宿主不重写」的唯一保证。可以在闸门里加一条：

```bash
grep -rE '^\s*(import|from)\s+(anthropic|openai|codex|hermes)' agent/ && echo "违反平台无关红线" && exit 1
```

### 这条设计对现有系统意味着什么

现在「同一套流水线」被写在好几个地方各写了一遍调度（WorkBuddy 写稿、Trae 兜底、Trae 周排期、Hermes 播客提醒）。
三层解耦之后，**调度只剩「谁唤醒」这一件事的差异**，其余全部收敛——这才是「收成一个 Agent」的实质。

> **2026-09-21 更正**：上面这句里的「Trae 兜底 / Trae 周排期 / Hermes 播客提醒」**三处都不存在**
> （用户确认 Trae 侧没挂任务；Hermes 早停用）。现役只有 **WorkBuddy 自动化 + 豆包 App**。
> 解耦结论不变，只是要收敛的东西比这里写的少。实测表见 `定时任务.md` 文件头，详见 §13.4。

---

## 4. 六层设计

### 4.1 E 执行循环

**设计决策**

- 外层是**带状态的固定管线**，每一步是「确定性脚本调用」或「交给 WorkBuddy 写稿」，终止条件全部是**代码可判的规则**，不是模型自评（checklist 红线：让模型给自己判卷 = 循环论证）。
- 断点续跑：每步开始/结束各写一条事件，重入时从 `episodes.stage` 继续。
- 防跑飞三道保险：**轮数上限**（写稿最多 2 轮、审稿回环最多 1 轮、合成最多 2 次）、**积分预算**（单期 token 上限，超了停机不硬跑）、**每步超时**（准备 20min、写稿 180min、验收 2min、审稿 30min、合成等待 90min、兜底合成 120min）。

**落地规格**

```python
# agent/pipeline.py
STAGES = ["prepare", "draft", "verify", "review", "handoff", "await_synth", "fallback", "publish"]

def run_episode(date: str, upto: str | None = None) -> EpisodeState:
    """从 episodes.stage 断点续跑，跑到 upto（含）为止。返回终态。"""
```

每一阶段的行为表：

| stage | 干什么 | 谁执行 | 失败处理 |
|---|---|---|---|
| `prepare` | 待消费闸 → fetch → 选料 → clone | 本机脚本 | fetch 全失败 → `abort`，不覆盖旧稿 |
| `draft` | 读源码写稿 + 写拆解笔记 | **WorkBuddy 会话** | 超时/未落盘 → 重试第 2 轮（把上轮闸门失败原因喂回去）；仍失败 → 保留旧稿，标 `draft_failed` |
| `verify` | 跑闸门，写 `latest-status.txt` | 本机脚本 | 不过 → 回 `draft`（算一次 attempt） |
| `review` | 独立审稿：只挑错，产出问题清单 | **WorkBuddy 新会话**（独立上下文） | 有问题 → 回 `draft` 改一轮；第二轮不再触发（防烧额度） |
| `handoff` | 推稿子到飞书 + 产出合成契约 | 本机脚本 | 失败只记日志，不回退阶段 |
| `await_synth` | 等豆包出成品 | 本机轮询 | 到 `synth_expect_by` 仍无成品 → `fallback` |
| `fallback` | 本地 VoxCPM2 合成 | 本机脚本 | 失败 → `no_audio`，推飞书告警 |
| `publish` | 上传网易云 | 本机脚本 | 登录态失效 → 停下推飞书，不重试 |

**为什么 `review` 排在 `verify` 后面，不是前面**（用户 2026-09-21 确认加审稿环节，顺序是我定的）：

机械闸门**免费、快、判据确定**；审稿 agent **要烧额度**。所以「先让便宜的把关，贵的后跑」——稿子连字数、字段、具体值密度都不够，根本不必浪费额度去审内容。反过来把 review 放前面，等于每期固定多烧一笔，且大概率审的是个半成品。

**审稿 agent 的四条硬约束**（防它变成第二个写稿的、防把额度烧穿）：

| 约束 | 具体做法 | 为什么 |
|---|---|---|
| **独立会话** | review 必须新开会话，不复用 draft 的会话 | 复用了就是自己审自己，产出的是自我辩护，不是挑错 |
| **只挑错不重写** | prompt 禁止输出改写后的正文，只输出结构化问题列表 | 一旦允许它改，它就会「顺手重写」，变成第二个写稿的：额度翻倍、责任不清 |
| **最多一轮** | `max_review_rounds: 1`。第二轮 draft 改完直接 verify → handoff | 跟「宁可短也别当天没稿」同一条原则：改稿不能把出稿卡死 |
| **复用同一份规范** | 审稿判据 = `write-episode-prompt.md` + skill `podcast-depth-writing`，**不另写一套** | 两份规范必然漂移，等于自己给自己再造一个「口径对不上」 |

**审稿审什么**（全部可判定，不评品味）：

| 审点 | 判据来源 |
|---|---|
| 每个设计点有没有说「解决什么问题 + 不做会怎样」 | prompt 的「禁 what without why」 |
| 每个设计点是不是四句话结构（怎么做 / 为什么必须这么做 / 代价是什么 / 换成默认做法会怎样） | skill `podcast-depth-writing` |
| 有没有翻案腔（「你以为…其实…」） | 项目红线 |
| 有没有注水（同一设计点换说法、抽象演绎、比喻填字） | prompt 的「绝对禁止」 |
| 有没有复述上一期讲过的内容 | `output/episodes.log` + 上一期稿子 |
| 事实与数字在拆解笔记里有没有出处 | 笔记的「取证台账」一节 |
| 「本周新闻」节有没有对 `output/news-covered.md` 去重 | prompt §5.5 |

**不做品味判断**（不评「这个比喻好不好」）——那是人工抽听时的事，机器硬评只会得到假分数。

**产物**：`output/<日期>-review.md`（审稿报告），落盘并记进 `episode_events`，改稿时作为输入喂回 `draft`。

**外环和内环怎么交界**（这是可编码的关键）：外环不「调用」WorkBuddy，而是**通过文件契约请求**——`agent/request.json` 写下这一轮要拆哪些仓库、读哪些文件、卡片上写了什么，WorkBuddy 自动化读它、干完把稿子落盘、写 `agent/done.json`。外环只看 `done.json` 和产物 mtime，**不关心会话内部发生了什么**（跟豆包那班同一套松耦合思路，已验证有效）。

### 4.2 T 工具注册

**设计决策**

- **固定管线 + 显式工具表**。工具表在 `config/tools.json`，声明命令、超时、是否可写、失败语义。状态机按管线调用，**不给模型自由 function-calling**（见 2.0 的编排决策）。
- 读写分离：`writable: false` 的工具外环永不重试写操作；`writable: true` 的必须带幂等键。
- 唯一例外：`draft` 阶段放给 WorkBuddy 会话，让它自由使用 Read / Grep / Bash——**这是刻意的**，因为「读哪些文件、怎么读」正是写稿质量的一部分，不能被写死成管线。

**落地规格**

```python
# agent/tools.py
@dataclass
class ToolSpec:
    name: str
    cmd: list[str]          # ["python3", "fetch.py"]
    cwd: str                # 项目根
    timeout_s: int
    writable: bool
    on_fail: str            # "abort" | "retry" | "degrade" | "continue"
    idempotent: bool

def call(spec: ToolSpec, args: list[str] = ()) -> ToolResult:
    """subprocess 执行，落 ep 事件，返回 ToolResult。"""
```

登记的工具（**分批落地，一期只登记主干**）：

| 名称 | 命令 | 可写 | 失败语义 |
|---|---|---|---|
| `prep` | `PREP_ONLY=1 bash scripts/daily-prepare.sh` | 是 | abort |
| `verify` | `bash scripts/verify-episode.sh <date>` | 是（写状态文件） | retry |
| `split` | `python3 scripts/split_segments.py <稿> 4.0 <dir>` | 是 | abort |
| `tts_local` | `python3 scripts/tts_local.py --input <稿> --output <m4a> --denoise deesser` | 是 | degrade |
| `upload` | `bash scripts/pipeline.sh upload <file>` | 是 | abort |
| `push_script` | `python3 scripts/feishu_sync.py --push-script --date <date>` | 是 | continue |
| `notify` | `python3 scripts/selection_push.py --title ... --summary ...` | 是 | continue |

`verify-episode.sh` 这一条**我不建议重写**：它是当前唯一的判据入口，重写会同时动 `daily-prepare.sh` 和写稿 agent 两个调用点。改为**薄包装**——脚本保留，内部把判据从 `config/agent.json` 读（下一步才做，见第 12 节）。

### 4.3 C 上下文管理

**设计决策**

- 每期**新开会话**，不复用上一期的上下文（平台会话上下文不可控，复用它等于把不确定性引进来）。跨期的信息靠 SQLite + 文件传，不靠会话记忆。
- 写稿会话的上下文预算是**分段式**，不是一次性灌：
  1. 骨架：skill 流程 + 当日清单 + 已选项目 → 约 4K 字，固定注入
  2. 索引：先只给「候选文件清单」（文件名 + 行数 + 一句话猜测），不读内容
  3. 深读：按清单挑文件逐个读，**单文件上限 800 行**（超出用 offset/limit 分段，不整篇灌）
  4. 沉淀：每读完一个文件，把结论写进拆解笔记（**落到文件，不留在上下文里**）
- 这条策略直接决定了积分花多少：**「结论落文件」是省额度的手段，不是写作规范**。上下文里只保留「当前在读哪个文件 + 已确认结论的指针」。

**落地规格**：策略写在 skill 里（prompt 层），代码不强制。可机械验的部分交给闸门：`episode_events` 里记 `files_read` 计数，低于 6 个文件判「读得太浅」并提示。

### 4.4 S 状态存储

**设计决策**

- **一张 `episodes` 表是期次状态的唯一真相源**，替代现在「靠文件 mtime 猜」的多个地方。
- **事件表只追加**（event-sourcing）：任何状态变化留一条带时间戳的事件，出问题能回放「那晚到底发生了什么」。
- 文件仍是**产物**的真相源（稿子、笔记、音频），DB 只存指针 + 指标 + 状态，不做第二份内容副本。
- 并发：SQLite 开 WAL；外环单写，workbench_server 只读（它现在是读写混合，新表这边只给读）。

**落地规格**：见第 7 节数据结构 + 第 6.4 节写入接口。

### 4.5 L 生命周期钩子

**设计决策**

- **闸门即钩子**。现在的 `verify-episode.sh` 已经是半个钩子层了，把它正式化。
- 拦截点分四类，每个都对应一次真实的历史事故：

| 钩子 | 拦什么 | 对应事故 |
|---|---|---|
| `pre_draft` | 项目黑名单、期次占用、待消费闸 | 「拿已停服项目当现役讲」 |
| `pre_synthesis` | 质量闸（字数/密度/字段/时效） | 「一路滑到 23 分钟」「没读源码就写」 |
| `pre_upload` | 文件存在 + 大小 + 时长合理 | 上传半截文件 |
| `on_failure` | 降级决策（写稿失败不覆盖旧稿；合成超期走本地） | 「套1失败没覆盖 → 豆包把上一期重录一遍」 |

- 审批点只留两个，其余全自动：**周选题确认**（现在就是人工，保留）、**豆包登录态/额度失效**（推飞书等人）。
- 纵深：黑名单**两层拦**——prompt 里写规则（事前）+ 闸门代码校验稿子开头 8 行（事后）。单点拦截会被绕过，这是 checklist 的要求。

**落地规格**

```python
# agent/gates.py
@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str
    metrics: dict[str, int | float]

def run_gate(name: str, date: str, cfg: dict) -> GateResult: ...
def pre_synthesis(date: str) -> list[GateResult]: ...
```

### 4.6 V 评估接口

**设计决策**

- **独立读路径**（CQRS）：验收只读产物、只写状态，绝不经过生成路径。这一点现有脚本已经做对了（注释里明写「只读稿子、只写状态文件」），继续保留。
- 指标全部**确定性**，不引入模型评分：汉字数、含具体数字的行数、字段标题数、字节数、黑名单命中、推算时长 vs 实测时长偏差。
- **主观质量分两级处理，不进自动评分**——「讲得好不好听」没有 ground truth，硬做只会得到假分数：
  1. **审稿 agent 初审**（2026-09-21 用户确认加）：独立会话、只挑错不重写，只做**可判定的那部分**（有没有 what without why、有没有注水、有没有翻案腔），不评品味。规格见 §4.1。
  2. **人工抽听复核**：每 7 期一次，结果记进 `episode_events`（`event='human_review'`）。
  诚实边界：审稿 agent 能防「明显的偷懒」，**防不了「张冠李戴」**（引用是真的、结论却用错了）——后者仍需人工兜底。这是 checklist 里「诚实边界」明确点出的那条。

**落地规格**

```python
# agent/gates.py
def report(date: str) -> str:
    """人话版一期体检报告：各指标 + 与上一期对比 + 是否退化。"""
```

---

## 5. 模块 / 目录结构

```
github-podcast/
├── agent/                          # 新增：Agent 层（平台无关，纯 Python 标准库）
│   ├── __init__.py
│   ├── pipeline.py                 # 外环：状态机 + 断点续跑 + 重试/降级
│   ├── stages.py                   # 8 个阶段的实现（prepare/draft/verify/review/...）
│   ├── tools.py                    # 工具注册与调用（读 config/tools.json）
│   ├── gates.py                    # 闸门实现（判据读 config/agent.json）
│   ├── state.py                    # SQLite 读写（episodes / episode_events / agent_runs）
│   ├── request.py                  # 生成 agent/request.json（给 WorkBuddy 会话的请求契约）
│   ├── schema.sql                  # 建表语句（幂等，可重复执行）
│   └── cli.py                      # 命令行入口：run / status / report / retry
├── config/
│   ├── agent.json                  # 新增：全部口径（时间/阈值/模型/降级）
│   └── tools.json                  # 新增：工具表
├── ~/.claude/skills/podcast-agent/  # 新增：智能规范（在**三家共用的软链库**里，不是 WorkBuddy 专属目录）
│   └── SKILL.md                     # 读 request.json → 写稿 → 写 done.json；平台无关
├── scripts/                        # 现有 28 个脚本：不动，它们是工具层
├── output/                         # 产物：稿件 / 笔记 / 音频 / 日志（不变）
├── cache/                          # 源码工作区（不变）
└── info_source.db                  # 加 3 张表
```

**新增代码量估计**：`agent/` 约 700-900 行 Python（含注释），`SKILL.md` 约 100 行，两个 JSON 配置约 120 行。**不删不改任何现有脚本。**

---

## 6. 关键接口签名

### 6.1 数据源接口

```python
# agent/state.py —— 全部读写都走这里，别处不直接连库
def connect(db_path: str = "info_source.db") -> sqlite3.Connection:
    """开 WAL，row_factory=sqlite3.Row。"""

def current_episode(conn: sqlite3.Connection, date: str) -> Episode | None: ...
def create_episode(conn: sqlite3.Connection, date: str, repos: list[str]) -> Episode: ...
def advance(conn: sqlite3.Connection, date: str, stage: str) -> None: ...
def fail(conn: sqlite3.Connection, date: str, reason: str) -> None: ...
def log_event(conn: sqlite3.Connection, date: str, event: str, detail: str = "") -> None: ...
def next_ep_no(conn: sqlite3.Connection) -> int:
    """max(episodes.ep_no)+1；首次从 output/episodes.log 行数回填。"""
```

### 6.2 工具接口

```python
# agent/tools.py
def load_tools(path: str = "config/tools.json") -> dict[str, ToolSpec]: ...
def call(spec: ToolSpec, args: tuple[str, ...] = ()) -> ToolResult: ...
def call_by_name(name: str, args: tuple[str, ...] = ()) -> ToolResult: ...
```

```python
@dataclass
class ToolResult:
    name: str
    ok: bool
    exit_code: int
    stdout_tail: str      # 末 2000 字符，够排查
    stderr_tail: str
    duration_s: float
    timed_out: bool
```

### 6.3 钩子接口

```python
# agent/gates.py
@dataclass
class GateResult:
    name: str                     # "chars" | "density" | "fields" | "blacklist" | ...
    passed: bool
    detail: str                   # 人话，直接能贴进飞书告警
    metrics: dict[str, int | float]

def run_gate(name: str, date: str, cfg: GateConfig) -> GateResult: ...
def pre_synthesis(date: str, cfg: GateConfig) -> list[GateResult]: ...
def format_failure(results: list[GateResult]) -> str:
    """把没过闸的项拼成一段能喂回写稿 agent 的修改指令。"""
```

### 6.4 给 WorkBuddy 的请求/回执契约（外环 ↔ 内环的交界）

```python
# agent/request.py
def write_request(date: str, repos: list[str], brief: str) -> str:
    """写 agent/request.json，返回路径。brief = 当日清单摘要 + 拼盘建议。"""

def read_done(date: str) -> dict | None:
    """读 agent/done.json；不存在或日期不匹配则返回 None（说明会话没干完）。"""
```

`agent/request.json` 结构（`task` 字段区分这一轮是写稿还是审稿，同一套契约机制支持两种内环任务）：

```json
{
  "date": "2026-09-22",
  "ep_no": 12,
  "task": "draft",
  "repos": ["owner/a", "owner/b"],
  "brief": "当日清单摘要 + 为什么选这两个 + 拼盘要求",
  "require": {
    "prompt": "scripts/write-episode-prompt.md",
    "skill": "podcast-depth-writing",
    "model": "deepseek-v4.1-flash",
    "min_files_read": 6
  },
  "outputs": {
    "script": "output/latest-script.md",
    "script_dated": "output/2026-09-22-script.md",
    "breakdown": "output/2026-09-22-breakdown.md"
  }
}
```

审稿轮（`task="review"`）的 request，输入换成产物、输出换成报告：

```json
{
  "date": "2026-09-22",
  "ep_no": 12,
  "task": "review",
  "inputs": {
    "script": "output/latest-script.md",
    "breakdown": "output/2026-09-22-breakdown.md",
    "prev_script": "output/2026-09-21-script.md",
    "episodes_log": "output/episodes.log",
    "news_ledger": "output/news-covered.md"
  },
  "require": {
    "prompt": "scripts/write-episode-prompt.md",
    "skill": "podcast-depth-writing",
    "model": "deepseek-v4.1-flash",
    "mode": "review-only",
    "allow_rewrite": false
  },
  "outputs": { "review": "output/2026-09-22-review.md" }
}
```

`allow_rewrite: false` 是**冗余但必要的双保险**——prompt 里已经禁止重写，配置里再声明一次，防止 prompt 被改动后失去约束。

`agent/done.json` 结构（写稿轮）：

```json
{
  "date": "2026-09-22",
  "task": "draft",
  "status": "ok",
  "files_read": 9,
  "chars": 9210,
  "notes": "两个仓库拼盘，二次深读落在 src/xxx.py",
  "model": "deepseek-v4.1-flash"
}
```

审稿轮的回执带结构化问题列表——**这就是「只挑错不重写」的落地形态**，稿子一个字都不由它改：

```json
{
  "date": "2026-09-22",
  "task": "review",
  "status": "issues_found",
  "issue_count": 3,
  "issues": [
    {
      "id": 1,
      "severity": "high",
      "type": "what_without_why",
      "where": "第 3 节第 2 段",
      "quote": "它内部用了事件溯源",
      "problem": "只说了怎么做，没说解决什么问题、不做会怎样",
      "rule": "prompt 的「禁 what without why」"
    },
    {
      "id": 2,
      "severity": "medium",
      "type": "water",
      "where": "第 5 节",
      "quote": "换句话说……",
      "problem": "同一设计点换说法，未提供新信息",
      "rule": "prompt 的「绝对禁止」"
    }
  ],
  "model": "deepseek-v4.1-flash"
}
```

字段取值约定：

| 字段 | 取值 | 说明 |
|---|---|---|
| `task` | `draft` \| `review` | 外环按此路由到不同 prompt 与产物路径 |
| `status` | `ok` \| `issues_found` \| `failed` | 审稿轮不产出 `ok`，要么有问题要么没跑成 |
| `severity` | `high` \| `medium` \| `low` | **只有 `high` 会触发改稿回环**，medium 及以下只记录 |
| `type` | `what_without_why` \| `water` \| `echo_prev` \| `no_source` \| `flip_tone` \| `news_dup` | 六类对应 §4.1 那张审点表，一一可查 |

---

## 7. 核心数据结构

### 7.1 状态结构（SQLite）

```sql
CREATE TABLE IF NOT EXISTS episodes (
  ep_no            INTEGER PRIMARY KEY,
  date             TEXT NOT NULL UNIQUE,
  stage            TEXT NOT NULL,     -- prepare|draft|verify|handoff|await_synth|fallback|publish|done
  status           TEXT NOT NULL,     -- running|ok|short|failed|no_audio
  repos            TEXT,              -- JSON 数组
  script_path      TEXT,
  breakdown_path   TEXT,
  audio_path       TEXT,
  chars            INTEGER,
  value_lines      INTEGER,
  est_minutes      REAL,
  actual_minutes   REAL,
  attempt          INTEGER DEFAULT 0,
  synth_route      TEXT,              -- doubao_app | local_voxcpm2
  model            TEXT,
  fail_reason      TEXT,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS episode_events (   -- 只追加，不更新不删除
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  date   TEXT NOT NULL,
  ts     TEXT NOT NULL,
  stage  TEXT,
  event  TEXT NOT NULL,   -- stage_start|stage_ok|stage_fail|degraded|human_review|note
  detail TEXT
);

CREATE TABLE IF NOT EXISTS agent_runs (       -- 每次外环启动一行，用于算额度与耗时
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  date       TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at   TEXT,
  exit_stage TEXT,
  exit_reason TEXT,
  model_calls INTEGER DEFAULT 0,
  est_tokens  INTEGER DEFAULT 0
);
```

### 7.2 运行时结构（Python）

```python
@dataclass
class Episode:
    ep_no: int
    date: str
    stage: str
    status: str
    repos: list[str]
    script_path: str | None
    breakdown_path: str | None
    audio_path: str | None
    chars: int | None
    value_lines: int | None
    est_minutes: float | None
    actual_minutes: float | None
    attempt: int
    synth_route: str | None
    model: str | None
    fail_reason: str | None

@dataclass
class StageOutcome:
    stage: str
    ok: bool
    next_stage: str | None      # None = 终止
    retryable: bool
    detail: str
```

### 7.3 配置结构

```python
@dataclass
class GateConfig:
    min_fields: int
    min_bytes: int
    min_value_lines: int
    require_one_of_sections: list[str]
    min_chars: int
    fail_below_chars: int
    blacklist_file: str
    blacklist_head_lines: int
```

---

## 8. 配置文件格式

### 8.1 `config/agent.json`

```json
{
  "version": 1,
  "project_root": "<项目根目录>",

  "schedule": {
    "draft_at": "00:34",
    "synth_expect_by": "02:40",
    "fallback_at": "03:00"
  },

  "models": {
    "drafting": "deepseek-v4.1-flash",
    "allow_switch": false
  },

  "budget": {
    "max_tokens_per_episode": 120000,
    "max_attempts_draft": 2,
    "max_synth_attempts": 2,
    "max_projects_per_episode": 2,
    "min_files_read": 6,
    "max_review_rounds": 1
  },

  "timeouts_s": {
    "prepare": 1200,
    "draft": 10800,
    "verify": 120,
    "await_synth": 5400,
    "fallback": 7200,
    "publish": 600
  },

  "gates": {
    "breakdown": {
      "min_fields": 10,
      "min_bytes": 8000,
      "min_value_lines": 20,
      "require_one_of_sections": ["二次深读", "取证台账", "取舍台账"]
    },
    "script": {
      "require_info_deadline": true,
      "blacklist_file": "scripts/blacklist-projects.txt",
      "blacklist_head_lines": 8
    },
    "length": {
      "min_chars": 8500,
      "fail_below_chars": 6500,
      "chars_per_minute": 168
    }
  },

  "review": {
    "enabled": true,
    "max_rounds": 1,
    "trigger_severity": "high",
    "allow_rewrite": false,
    "checks": ["what_without_why", "water", "echo_prev", "no_source", "flip_tone", "news_dup"],
    "model": "deepseek-v4.1-flash",
    "report_path": "output/{date}-review.md"
  },

  "synth": {
    "primary": "doubao_app",
    "fallback": "local_voxcpm2",
    "pace": 4.0,
    "segment_target_chars": 480,
    "denoise": "deesser",
    "duration_ratio_accept": [0.8, 1.2]
  },

  "upload": { "target": "netease_cloud", "cli": "ncm-cli" },

  "notify": { "feishu": true, "on": ["draft_failed", "no_audio", "upload_failed"] }
}
```

字段说明：

| 字段 | 含义 | 改它意味着 |
|---|---|---|
| `schedule.draft_at` | 主班起跑时间（**注意：真正生效在 WorkBuddy 自动化面板，这里只是文档镜像**） | 要同时改面板 |
| `budget.max_projects_per_episode` | 一期最多拼几个仓库 | 从 3 降到 2 = 省额度但可能变短 |
| `gates.*` | 全套闸门判据 | **改判据只改这里**（这是治口径漂移的关键） |
| `review.enabled` | 审稿环节总开关 | 想省额度时关掉，流程其余部分完全不变 |
| `review.trigger_severity` | 只有达到这个严重度才回炉改稿 | 调成 `medium` 会更严，但改稿回环更多、更烧额度 |
| `review.checks` | 审哪几类问题 | 关掉某一类 = 那一类不再报，先砍它再考虑关整个环节 |
| `synth.primary/fallback` | 合成主路线与降级路线 | 以后想换合成方案就改这一行 |
| `synth.duration_ratio_accept` | 实测时长 / 推算时长 的容许区间 | 超出即告警，防「稿子写够了但音频只有 20 分钟」 |

### 8.2 `config/tools.json`

```json
{
  "version": 1,
  "tools": [
    {
      "name": "prep",
      "cmd": ["bash", "scripts/daily-prepare.sh"],
      "env": { "PREP_ONLY": "1" },
      "timeout_s": 1200,
      "writable": true,
      "idempotent": false,
      "on_fail": "abort"
    },
    {
      "name": "verify",
      "cmd": ["bash", "scripts/verify-episode.sh"],
      "timeout_s": 120,
      "writable": true,
      "idempotent": true,
      "on_fail": "retry"
    },
    {
      "name": "tts_local",
      "cmd": ["python3", "scripts/tts_local.py"],
      "timeout_s": 7200,
      "writable": true,
      "idempotent": false,
      "on_fail": "degrade"
    },
    {
      "name": "upload",
      "cmd": ["bash", "scripts/pipeline.sh", "upload"],
      "timeout_s": 600,
      "writable": true,
      "idempotent": false,
      "on_fail": "abort"
    }
  ]
}
```

---

## 9. 层间交叉检查

| 关系 | 说明 | 本设计怎么处理 |
|---|---|---|
| **E 终止 ← V 判定** | 循环的终止条件必须来自 V 的确定性判据，不能是模型自评 | `stages.verify` 调 `gates.pre_synthesis()`，返回 `GateResult` 列表；全过才进 `handoff` |
| **S 写入 ← L 拦截** | 状态变更必须经过钩子记账，否则等于没留痕 | `state.advance()` 内部强制写 `episode_events`；不允许别处直写 `episodes.stage` |
| **C 清理 ← E 成本** | 上下文策略直接决定积分花多少 | 「结论落文件」策略 + `max_projects_per_episode=2` + 单文件 800 行上限，三条共同构成积分闸 |
| **T 可写 ← L 审批** | 可写工具必须先过 `pre_*` 钩子 | `tools.call()` 在 `writable=true` 且 `idempotent=false` 时，先查同类操作是否已在 `episode_events` 里成功过，防重复上传/重复合成 |
| **E 重试 ← S 断点** | 重试次数与断点位置必须同源，否则会重复烧额度 | `attempt` 存 DB，重启后从 `attempt` 与 `stage` 双读 |
| **V 审稿 ← E 回环** | 审稿只审可判定项、只有 high 才触发回环，且最多回一次 | 外环读 `done.json` 的 `issues`，用 `trigger_severity` 过滤后才决定是否回 `draft`；`max_review_rounds` 兜底 |
| **V 审稿 ← C 上下文** | 审稿必须新会话，否则等于自己审自己 | 外环为 `task=review` 单独写入一份 request，不复用 draft 会话 |

---

## 10. 六层决策表

| 层 | 决策 | 依据 | 状态 |
|---|---|---|---|
| E 执行循环 | 双环：外环本机 Python 状态机 + 内环 WorkBuddy 会话；断点续跑；三道保险（轮次/预算/超时） | 反例推演：单会话跑全程会因长任务不可续而双倍烧额度 | 默认假设 |
| T 工具 | 固定管线 + 显式 `tools.json`；工具 = 现有 CLI 脚本，不改写 | checklist 警告「固定管线配动态工具表」是过度设计 | 已确认（沿用现状） |
| C 上下文 | 每期新会话；索引→深读→结论落文件；单文件 800 行 | 会话不可控 + 积分预算 | 默认假设 |
| S 状态 | SQLite 复用 `info_source.db`，3 张新表；事件只追加 | 根治「靠 mtime 猜状态」 | 默认假设 |
| L 钩子 | 闸门即钩子，4 个拦截点；审批只留 2 处 | 每个钩子对应一次真实历史事故 | 已确认（周选题保留人工） |
| V 评估 | 独立读路径 + 全部确定性指标；主观质量拆两级：审稿 agent 初审（只审可判定项）+ 人工抽听复核 | checklist「引用校验独立于生成路径」+「诚实边界」 | 已确认（审稿环节 2026-09-21 用户拍板） |

---

## 11. 参考架构图

```
                 ┌────────────────────────────────────────────┐
                 │  WorkBuddy （harness：模型 / 工具 / 循环）   │
                 │                                            │
   00:34 自动化 → │  读 SKILL.md → 读 agent/request.json       │
                 │      ↓ 内环 A：读源码、写稿（自由循环）      │
                 │      ↓ 内环 B：换新会话审稿（只挑错、不重写） │
                 │      两条内环都用 deepseek-v4.1-flash        │
                 │      ↓ 落盘 *.md + *-review.md             │
                 │  写 agent/done.json                        │
                 └───────────────────┬────────────────────────┘
                                     │ 文件契约
                 ┌───────────────────▼────────────────────────┐
                 │  外环  agent/pipeline.py （本机，零模型成本）│
                 │  prepare → draft → verify → review → handoff │
                 │  ┌──────────────────────────────────────┐  │
                 │  │ SQLite: episodes / events / runs     │  │
                 │  └──────────────────────────────────────┘  │
                 └───────────────────┬────────────────────────┘
                                     │ 契约文件（格式不变）
                    latest-script.md + latest-status.txt
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        ▼                                                         ▼
┌──────────────────┐                                    ┌──────────────────┐
│ 豆包 App 02:00   │                                    │ 兜底 launchd     │
│ seed-audio 合成  │─── 02:40 还没成品？ ───→            │ 03:00 本地       │
│ ↓ 上传网易云     │                                    │ VoxCPM2 顶一版   │
└──────────────────┘                                    └────────┬─────────┘
                                                                  ▼
                                                          上传网易云云盘
```

---

## 12. 遗留问题与未知区（诚实标注）

### 12.1 需要你拍的点

1. **积分到底够不够，现在算不出来。**
   WorkBuddy 免费版是「每月 500 积分」，但**一积分等于多少 token、写稿这种长任务一晚上扣多少，我查不到公开口径**。一期要读 6-10 个文件 + 产出 9000 汉字，我按经验估 6-10 万 token。
   → **建议做法**：先按本设计跑一期，跑完看积分消耗，用实测值决定频率（每天 / 隔天）。`agent_runs.est_tokens` 表就是为这个留的。
   → **若不解决**：编码时先按「每期必记积分差值」写，先不设自动停机的硬阈值。

2. **自动化任务能不能指定模型，文档里没写。**
   我查了 WorkBuddy 文档，只有套餐页写了「Auto 模型调度（限免全模型）」，没说自动化任务能否锁定某个模型。
   → **建议做法**：在自动化 prompt 里显式写一条「本次任务全程使用 DeepSeek-V4.1-Flash，不要切换模型」；若面板上能选，以面板为准。
   → **若不解决**：写稿质量可能因模型漂移而波动，先靠闸门兜住下限。

3. **拼盘从 3 个降到 2 个，是我为了省额度提的，要不要接受。**
   实测数据：三项目拼盘 → 9910 汉字 ≈58 分钟；单项目 → 3600-4025 汉字 ≈24 分钟。降到 2 个大概率落在 6500-8500 之间，**会触发 `SHORT` 标记**（能听但偏短）。
   → **建议**：先保 3 个（质量优先），把省额度放在「读文件更省着读」上；如果积分实测撑不住，再降到 2 个。

4. **审稿 agent —— 2026-09-21 用户已拍板：加。**
   规格见 §4.1（独立会话 / 只挑错不重写 / 最多一轮 / 复用同一份规范），配置项见 §8.1 的 `review` 段，回执结构见 §6.4。
   → **剩下的待观察点**：它是新增的额度消耗方（每期多读一遍全文 + 产出一份问题清单）。建议头 3 期实测积分，若超预算，收窄顺序是：① 把 `review.checks` 从 6 类砍到 2 类（只留 `what_without_why` 和 `water`）；② 再不行才关 `review.enabled`。**不建议一上来就关**——它拦的正是闸门拦不住的那一类问题（写得够长但没讲透）。

### 12.1b 关于「多 Agent」的定性（一次说清，免得后面反复）

问：这套东西本质上是「多 Agent」吗？

**答：不是。** 准确描述是「**一条固定流水线 + 几个智能调用点**」。

| | 多 Agent 协作 | 本系统 |
|---|---|---|
| 结构 | 多个 agent 互相通信、辩论、分工 | 步骤之间**严格顺序依赖**，无对抗、无协商 |
| 适用 | 没有固定流程、需要多视角碰撞的问题 | 流程完全固定（没抓源就没法选料，没选料就没法读源码） |
| 成本 | 每多一个 agent 就多一份上下文传递 | 单线调用，上下文只传一次 |

**硬拆成多 Agent 的代价**（魔鬼代言人的反例）：写稿 agent 读过的 8 个源码文件，审稿 agent 要再读一遍才能判断「有没有读透」——**免费额度直接翻倍**；而且出问题时定位困难（稿子不好，是写稿没写好还是审稿没拦住？）。

**唯一值得放第二个 agent 的位置是「评估」，这一点已由用户拍板采纳**（`stages.review`，规格见 §4.1）——因为那里有真正的对抗性：一个负责写，一个专职挑错。这也正是 harness 六层里 V 层的设计原则：评估不能自己判自己。

**顺带澄清一个概念**：WorkBuddy 的「专家团」**不是多 Agent 系统**。一个专家 = 一份人格 prompt（`agents/<name>.md`）+ 一个技能包（`skills/<skill>/SKILL.md`），100 个专家是 100 个**相互独立的单 agent**，不是一个系统里协作的 100 个 agent。所以「做成专家包」和「做成多 Agent」是两件不相干的事——前者是**分发形态**，后者是**运行结构**。

### 12.2 框架没覆盖、我判断不了的

- **豆包那班的可见性为零**。它什么时候跑、跑成功没有，Agent 只能通过「`output/audio/` 里有没有今天的成品」间接判断。这意味着**豆包跑了一半失败、留下了半截文件**这种情况，Agent 可能误判为成功。缓解手段是加一条文件名/时长合理性检查（`pre_upload` 钩子），但无法根治。
- **WorkBuddy 自动化的失败通知机制未知**。如果自动化半夜跑挂了，你现在是怎么知道的？这决定了 `notify` 钩子该往哪推。建议推飞书（已有通道）。
- **一积分 = 多少 token** 无公开口径（见 12.1）。

### 12.3 落地顺序建议（如果编码）

| 步 | 做什么 | 为什么先做 |
|---|---|---|
| 1 | `agent/state.py` + `schema.sql` + `cli.py status` | 没状态表，后面全是猜。这一步零风险，纯新增 |
| 2 | `config/agent.json` + `config/tools.json` | 口径先收拢，后面改行为不改代码 |
| 3 | `agent/tools.py` + `stages.prepare/verify` | 把确定性部分接上（不碰模型） |
| 4 | `.workbuddy/skills/podcast-agent/SKILL.md` + `request.py` | 把内环接上，跑一期真稿 |
| 5 | `stages.await_synth/fallback/publish` | 接上合成与上传，**补上「豆包失败就没兜底」这个洞**（旧兜底实际没在跑，见 §13.4） |
| 6 | 把新链路挂到定时任务上（**没有旧任务要停**：Trae 侧本来就没有任务，WorkBuddy 那条兜底是 PAUSED） | 最后一步才接线，前面跑通再动 |

---

## 13. 落地记录（2026-09-21）

**第 1-5 步已编码完成**，第 6 步（拆旧）未动——旧链路照旧在跑，新链路**还没挂到任何定时任务上**。
代码在 `agent/`（8 个 py + schema.sql）、配置在 `config/agent.json` + `config/tools.json`、
内环规范在 `~/.claude/skills/podcast-agent/SKILL.md`（三家共用的软链库，不是 WorkBuddy 专属目录）。

### 13.1 与设计稿不一致的四处（都是核对实际接口后改的）

| 地方 | 设计稿写的 | 实际落地 | 为什么 |
|---|---|---|---|
| `next_ep_no` 回填 | §6.1「首次从 `output/episodes.log` 行数回填」 | 从 `output/episodes/ep<N>-*/` 目录名回填 | **原话是错的**：episodes.log 一行一个**仓库**（还有 `topic:xxx`），到 09-21 是 37 行，真实期号是 15。拿行数当期号会一次跳掉二十多期 |
| `notify` 工具 | §4.2 用 `scripts/selection_push.py --title … --summary …` | 新增 `agent/notify.py`，走 `lark-cli im +messages-send --text` | 那个脚本的语义是「先写本地选题库，再同步飞书」——拿它当告警通道，会在选题库里堆出一行行**假选题**。告警与选题不能共用一个写入口 |
| 目录结构 | §5 列了 9 个文件 | 多一个 `agent/paths.py` | 路径解析要能被 gates / stages / request 共用，放 `state.py` 里语义不对；放各文件里重算路径，在 launchd / 不同 cwd 下最容易出错 |
| 表字段 | §7.1 的 `episodes` 16 列 | 多 `review_round`、`files_read` 两列 | `max_review_rounds` 的计数必须落库（外环重启后不能「忘了已经审过一轮」，那会把额度烧穿）；`files_read` 是 §4.3 容器预算的留痕点 |

另外 `tools.json` 比 §8.2 多了 `upload_local` / `split` / `notify` / `ffprobe` 四条——都是 fallback 与 publish
两阶段真会用到的；`ffprobe` 是只读（量实测时长，不判死只记录）。

### 13.2 顺手修掉的两个真 bug

1. **黑名单闸从 09-14 立起到 09-21 一次都没拦过**（`scripts/verify-episode.sh`）。
   两个 bug 互相掩盖：① 把黑名单整行（含行尾 `\t# 官方口径…` 注释）当匹配串，`grep -F` 永远匹配不到；
   ② 那一行 `fail "…「$proj」（…"` 里全角括号紧跟变量名，`set -u` 下必崩——因为 ① 让 `fail` 从来没执行到，
   ② 一直没暴露。两个都修了，并**按项目规矩重跑了正负样本**（Gemini CLI / gitleaks 判 FAILED，现役项目放行）。
2. **`scripts/local-fallback.sh` 的「今天有没有成品」判据永远不成立**（第 39 行 `ls output/audio/${TODAY}*.m4a`）。
   豆包产物叫「项目名-播客完整版-NNmin.m4a」，**名字里没有日期**——豆包明明出了成品，本地兜底还会白跑两小时 GPU。
   新链路按 mtime 判（`agent/tools.py` 的 `newest_product`）。**旧脚本没动**，等第 6 步拆旧时一起退役。

### 13.3 落地时新加的两条保守设计

- **闸门跑两遍**：Python 闸给结构化指标，`verify-episode.sh` 仍是唯一入口、由它写 `latest-status.txt`
  （豆包那班的契约，§1.1）。两者结论不一致时记 `gate_drift` 事件并**以脚本为准**。
  这样既能立刻用上结构化指标，又不用在「薄包装」落地前赌两处判据完全等价。
- **降级合成多一道 `script_fresh` 闸**：稿子超过 12 小时就不合成（同豆包那班的闸 b）。
  超龄还合成 = 把上一期重录一遍，正是文档里记过的事故。

### 13.4 还没做 / 待你定

- **三个待拍项照旧**（§12.1 的第 1-3 条）。配置里先按建议值落了：`max_projects_per_episode: 3`（建议保 3）、
  `max_tokens_per_episode` 只记账不硬拦（积分换算查不到公开口径）。
- **`chars_per_minute` 填的是 168，不是 170-185**。理由是让它**跟着闸门脚本走**，DB 里的数与
  `latest-status.txt` 里的数完全一致，漂移检测才有意义。写稿 prompt §0.5 主张 170-185 那处没裁决前，
  不单方面改——否则就是又造一个「口径对不上」。裁决后只改这一个数。
- **旧兜底实际上没在跑（2026-09-21 收紧口径）**。原文写「旧兜底还挂着」是**错的**：
  用户确认 **Trae 侧没有挂任何任务**，WorkBuddy 面板里那条「播客本地兜底」（03:00）是 **PAUSED**。
  → **豆包那班失败时当前没有任何兜底**（ep15 缺音频就是这么来的）。这也让 `agent/launchd/`
  那个 plist 的价值变高了：它补的正是这个洞，装它不需要先停谁。
  前提清单（新链路跑通一期真稿 / 确认旧兜底确实停着 / 不再依赖旧判据）见 `agent/launchd/README.md`。
- **「调度散在四处」这个前提也要跟着改**：设计稿 §0 与 §3.1 写的「WorkBuddy 写稿 / Trae 兜底 /
  Trae 周排期 / Hermes 播客提醒」里，**Trae 那两处和 Hermes 那处都不存在**，现役只有
  WorkBuddy 自动化 + 豆包 App（见 `定时任务.md` 文件头的实测表）。三层的解耦结论不变，
  只是「要收敛的东西」比设计时估的少。
