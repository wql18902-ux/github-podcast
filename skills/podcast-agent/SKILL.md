---
name: podcast-agent
description: |
  播客流水线的**内环**任务入口：宿主会话被外环请求时，按 agent/request.json 干「写稿」或「独立审稿」。
  两种 task 走完全不同的规矩——draft 是自由循环（读源码、写稿、写拆解笔记），
  review 是**只挑错不重写**（独立会话、结构化问题列表，一个字都不改稿）。
  触发：request.json 出现在 <项目根目录>/agent/ 下、
  「播客拆解」「播客夜班」「写今天这期」「审这一期」。
agent_created: true
---

# podcast-agent · 播客内环

> **单一真相源**：写稿规范原文在 `<项目根目录>/scripts/write-episode-prompt.md`，
> 深度框架在 `skills/podcast-depth-writing/SKILL.md`。本 skill 是**跨 Agent 的入口与契约说明**
> （任何认 `~/.codex/skills` 的 Agent 通用：Claude Code / Codex / WorkBuddy 同一份）。
> 冲突时以那两份为准。

## 什么时候用

外环（`agent/pipeline.py`）跑完 `prepare` 之后会写一个请求文件：

```
<项目根目录>/agent/request.json
```

看到它、并且 `task` 字段是本轮要干的活，就按下面执行。**先读 request.json，不要凭印象猜今天拆什么。**

## 第 0 步：读请求，分流

```bash
cat <项目根目录>/agent/request.json
```

| `task` | 干什么 | 谁来干 |
|---|---|---|
| `draft` | 读源码 → 写稿 + 写拆解笔记 | 会话 A（可以是当前这个） |
| `review` | 独立审稿：只挑错，产出问题清单 | **必须新开会话**（会话 B） |

`review` 必须新会话，不能复用 `draft` 的会话——复用了就是自己审自己，产出的是自我辩护，不是挑错。

> 硬约束（外环会检查，别绕）：
> - `require.model` 指定的模型全程不要换（`models.allow_switch: false`）。
> - **不许手写或改 `output/latest-status.txt`**：它是验收闸的所有权，也是豆包那班的入口契约。
> - **不许动 `fetch.py` 的 `QUERIES` / `KNOWN_CN_ORGS`**，不许改删 `output/episodes.log`。
> - 删除只进废纸篓，不 `rm -rf`。

---

## task = draft

### 1. 按规范全文执行

读并**全文执行** `scripts/write-episode-prompt.md`（那是执行手册，不要只扫标题）。
深度标准照 `skills/podcast-depth-writing/SKILL.md`：一个设计点 = 四句话
（具体怎么做带值 → 为什么必须这么做 → 代价是什么 → 换成默认做法会怎样）。

`request.json` 的 `brief` 里有：当日清单摘要、今天排期上写的选题、本期仓库、拼盘要求。
**排期与选料脚本不一致时以排期为准**，并在回执 `notes` 里写清为什么改了。

### 2. 体量与拼盘的现实约束

- 正文 ≥`gates.length.min_chars`（默认 8500 汉字 ≈51 分钟）
- **单项目写到 4000 字只够二十多分钟**——撑不起体量就必须拼盘，一期最多
  `budget.max_projects_per_episode` 个仓，每个都走完拆解 10 字段
- 加长只能靠「多读源码、多给机制级细节」，**禁止注水**（同一设计点换说法、抽象演绎、比喻填字）
- 至少碰 `budget.min_files_read` 个源码文件（默认 6）——回执里的 `files_read` 要如实报

上下文策略（省额度的手段，不是写作规范）：先拿「候选文件清单」再逐个深读，
**单文件上限 800 行**（超了用 offset/limit 分段），每读完一个文件就把结论写进拆解笔记——
**结论落文件，不留在上下文里**。

### 3. 产物（三件，路径以 request.json 的 `outputs` 为准）

| 文件 | 内容 |
|---|---|
| `output/latest-script.md` | 主稿（= `output/<日期>-script.md`，两个都要落） |
| `output/<日期>-breakdown.md` | 拆解笔记：≥10 字段标题、≥8000 字节、含具体数字的行 ≥20、且「二次深读 / 取证台账 / 取舍台账」**至少有一节** |
| `output/episodes/ep<N>-<slug>/page.md` | 期次页，开头要有机器可读声明行（`- repo:` / `稿子：` / `拆解笔记：` / `音频：`）——缺了这期在选题台上不存在 |

稿子开头必须有 `信息截止：YYYY-MM-DD`；拆解笔记必须有「信息截止」「当前版本」两栏。

### 4. 自己先过一遍闸再交

```bash
cd <项目根目录> && bash scripts/verify-episode.sh
```

没过就按它给的原因补料再跑，**不许跳过、不许手写状态文件**。

### 5. 写回执 `agent/done.json`

```json
{
  "date": "2026-09-22",
  "task": "draft",
  "status": "ok",
  "files_read": 9,
  "chars": 9210,
  "notes": "两个仓库拼盘；二次深读落在 src/xxx.py",
  "model": "deepseek-v4.1-flash"
}
```

`status` 只能是 `ok` | `failed`。`files_read` 与 `chars` **必填**——缺了外环按「没干完」处理，会退回重跑。
`date` / `task` 必须与 request.json 一致（外环靠它认领）。可选：把 `request_id` 原样抄回来。

### 6. 交还控制权

```bash
cd <项目根目录> && python3 -m agent.cli resume
```

---

## task = review

**这一轮的规矩与 draft 完全不同：你只负责挑错，一个字都不要改稿子。**

### 1. 输入

`request.inputs` 给了五样：本轮稿子、拆解笔记、上一期稿子、`output/episodes.log`、`output/news-covered.md`。
判据用 `request.require.checks`（六类），**不要另造一套标准**——两份规范必然漂移。

### 2. 只审「可判定」的，不评品味

| 审点 | 判据来源 |
|---|---|
| 每个设计点有没有说「解决什么问题 + 不做会怎样」 | prompt 的「禁 what without why」 |
| 每个设计点是不是四句话结构 | `skills/podcast-depth-writing/SKILL.md` |
| 有没有翻案腔（「你以为…其实…」） | 项目红线 |
| 有没有注水（同一设计点换说法、抽象演绎、比喻填字） | prompt 的「绝对禁止」 |
| 有没有复述上一期讲过的内容 | `output/episodes.log` + 上一期稿子 |
| 事实与数字在拆解笔记里有没有出处 | 笔记的「取证台账」一节 |
| 「本周新闻」节有没有对 `output/news-covered.md` 去重 | prompt §5.5 |

**不评「这个比喻好不好」**——那是人工抽听时的事，机器硬评只会得到假分数。

### 3. 产物

- `output/<日期>-review.md`：人看的审稿报告
- `agent/done.json`：

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
    }
  ],
  "model": "deepseek-v4.1-flash"
}
```

| 字段 | 取值 |
|---|---|
| `status` | `issues_found` \| `failed`（**审稿轮不产出 `ok`**：要么有问题，要么没跑成） |
| `severity` | `high` \| `medium` \| `low`——**只有 `high` 会触发改稿回环**，medium 及以下只记录 |
| `type` | `what_without_why` \| `water` \| `echo_prev` \| `no_source` \| `flip_tone` \| `news_dup` |

没找出问题就写 `"status": "issues_found", "issue_count": 0, "issues": []`，别写 `ok`。

### 4. 红线

- `allow_rewrite: false`（prompt 与配置里各声明了一次）：**不许输出改写后的正文**。
  一旦允许改，你就会「顺手重写」，变成第二个写稿的——额度翻倍、责任不清。
- 审稿最多回炉一轮（`review.max_rounds: 1`）。第二轮 draft 改完直接 verify → handoff，
  改稿不能把出稿卡死。

### 5. 交还控制权

```bash
cd <项目根目录> && python3 -m agent.cli resume
```

---

## 外环会怎么处置你的回执

- `draft` 回执 `status=ok` → 进 `verify`（机械闸）。没过闸会把失败原因写进下一轮 request 的 detail 喂回来。
- `verify` 过了才进 `review`（先让便宜的把关，贵的后跑）。
- `review` 报出 `high` → 回炉改一轮（消耗一次 `attempt`）；报 `medium` 及以下 → 直接交合成。
- 任何一步超时/失败都不会覆盖上一期稿件——宁可当天没新稿，也不能让豆包把上一期重录一遍。
