# Agent / 前沿 AI 地图（常驻，一处维护）

> 规则：产品换代只改这一处；每期页、拆解笔记、选题库都指过来（`[[agent-map]]`）。
> 最后核对：2026-09-11。
> 这张表原来散在第 5 期稿子里，现在提成单一真相源——以后某个产品换代了，改这里一次就够，旧稿不动（红线：旧稿只追加）。

| 家 | 现在的旗舰 | 旧角色（已被取代） | 记忆文件 | 标志性设计 | 来源 |
|---|---|---|---|---|---|
| Anthropic | Claude Code | — | `CLAUDE.md` + 自动记忆 | 30+ hook 事件、权限四档、checkpoint 快照、上下文当预算 | 第 5 期 + 官方文档 |
| OpenAI | Codex | — | `AGENTS.md` | worktree + 云隔离环境、多 agent 并行、也上 Skills | 第 5 期 |
| Google | **Antigravity（2.0）** —— agent-first 开发平台，含 CLI（命令 `agy`）/ IDE / 编辑器扩展 / Python SDK | Gemini CLI（开源终端 agent，Apache 2.0，`GEMINI.md`） | `AGENTS.md` | agent-first 平台化（从「一个终端 agent」升成「一整个开发平台」） | antigravity.google（官网原话「Google Antigravity is our agentic development platform」）、antigravity.org.cn（2026-09-11 核实） |
| Cursor | Cursor | — | `rules` 文件 | Plan Mode 先规划再动手、贵/便宜模型来回切 | 第 5 期 |
| Nous Research | Hermes Agent | — | `MEMORY.md` + `USER.md` | 记忆当头等公民 + curator + checkpoint | 第 3 期 + 本机源码 |

> ⚠️ 更正记录：第 5 期稿子把 Google 那格写成「Gemini CLI」，2026-09 实际主力已是 **Antigravity**。本表按现状记，旧稿不改（只在这里加更正指针）。

## 主题线

- **Agent 这层壳**（同一副骨架的两个切面：管记忆 / 管行动）
  - [[ep3-hermes-agent]]（管「机械底座怎么记」）
  - [[ep5-claude-code]]（管「机械底座怎么动」）
  - 共同结论：把智能用在理解上，把稳交给机械
- **算力取舍**（放弃用不上的精度，换可行性）
  - [[ep1-whisper-cpp]]（量化 / 针对性后端 / 反框架）
- **可视化装配**（把智能从「要写的程序」变成「要连的构件」）
  - [[ep4-n8n]]
- **攒下的东西怎么验**（2026-09-21 新开一条线，接 ep8–ep14 的「攒得住」）
  - [[ep15-assertions]]（把判据写成配置 / 装进管线 / 把攻击当判据：promptfoo · guardrails · garak）
  - 共同结论：跑过了不算数，得知道判据在什么情况下会骗你

## 国内大厂（2026-09-11 起纳入素材源，只收大公司）

| 家 | GitHub org | 官方发布 | 现状 |
|---|---|---|---|
| DeepSeek | `deepseek-ai` | `api-docs.deepseek.com/updates/` | 日更；最新论文 DeepSeek-V4（2026-04-26） |
| 千问（阿里） | `QwenLM` | `qwenlm.github.io/blog/`（真 RSS） | 日更；最新 Qwen3.5-Omni（2026-04-17） |
| 字节 | `bytedance` / `ByteDance-Seed` | `seed.bytedance.com` | 活跃；最新 Seed2.0（2026-06-30） |
| 智谱 | `zai-org` / `THUDM` | `docs.bigmodel.cn` | 活跃；**arXiv 按机构名搜不到**，只走 org + 官网 |

> 国内侧窗口：论文 60 天（用户 2026-09-11 拍板「两个月以内」），日常时效靠 GitHub org 日更 + 官方更新页撑。海外 arXiv 仍 14 天。
