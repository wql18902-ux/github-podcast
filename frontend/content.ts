/**
 * 真实内容模块 —— 每一项都能追到本仓自己的一个文件。
 *
 * 数据来源（只读，不改）：
 *   web/library/data/episodes.json   39 期的编号 / 标题 / 日期 / 汉字数 / 判断 / 仓库 / 音频
 *   web/library/data/auditions.js    2 段真实 MiMo 合成试听
 *   output/episodes/<slug>/page.md   每期的标的、本期一句话、关键证据
 *   output/episodes/<slug>/…breakdown.md   每期的源码级取证与二次深读
 *   cache/<repo>/README.md · CITATION.bib · paper.md   论文题名与作者的原件
 *
 * 反虚构纪律：title 与 note 都是按上面的文件抓出来的原文（不是转述、不是补写），
 * 每条上面用注释标了它来自哪个文件；统计与最近六期直接读 episodes.json 的数。
 * content.test.mjs 会把每条 note 拿回原文件逐字比对，抓不到就 exit 1。
 */

export type SourceKind = 'book' | 'paper' | 'repo';

export interface KnowledgeSource {
  kind: SourceKind;
  /** 真实题名，按 episode page / README 的原样，不虚构。 */
  title: string;
  /** 作者 / 机构 / 仓库 owner。仓库用 owner/name。 */
  byline: string;
  /** 一句话说清「这一项具体给了这一期什么」，引自该期页面原文。 */
  note: string;
  /** 只放有证据的标签。 */
  tags: string[];
  /** 来自第几期。 */
  episode: number;
  /** episodes.json 里那一期的真实日期。 */
  date: string;
}

export interface EpisodeCard {
  no: number;
  title: string;
  oneLiner: string;
  date: string;
  chars: number;
  minutes: number;
  series: string;
  url: string;
}

export const books: KnowledgeSource[] = [
  {
  // source: output/episodes/ep34-who-judges/2026-10-16-breakdown.md
    kind: 'book',
    title: '高效能人士的七个习惯',
    byline: 'Stephen R. Covey（英文原题 The 7 Habits of Highly Effective People，1989）',
    note: '1989 年柯维在《高效能人士的七个习惯》里把它做成四象限',
    tags: ['EP34', '书'],
    episode: 34,
    date: '2026-10-16',
  },
  {
  // source: output/episodes/ep32-borrowed-voice/2026-10-14-breakdown.md
    kind: 'book',
    title: '生活黑客',
    byline: '存档只记书名，未记作者、译者与版本',
    note: '引《生活黑客》里一个追求极致效率的程序员，每天高产出注意力的上限是 12 小时，而且那个状态只持续了一个月。',
    tags: ['EP32', '书'],
    episode: 32,
    date: '2026-10-14',
  },
];

export const papers: KnowledgeSource[] = [
  {
  // source: output/episodes/ep31-trust-the-done/2026-10-13-breakdown.md
    kind: 'paper',
    title: 'LLM Agents Can Easily Tamper With Their Own Traces（arXiv 2609.30266）',
    byline: 'arXiv 2026-09-24 预印本（cs.CR）；机构含 ELLIS Institute Tübingen / 马普智能系统研究所 / Exponential Security Labs / Snyk',
    note: '三个角度：① 能力——被直接要求删会话记录，几乎每次都照做；除 Muse Code（其 Muse Spark 记录 0% 攻击成功率）外全部未触发监控守卫。',
    tags: ['EP31', '预印本', 'cs.CR'],
    episode: 31,
    date: '2026-10-13',
  },
  {
  // source: output/episodes/ep36-self-feeding/2026-10-18-breakdown.md
    kind: 'paper',
    title: 'Nature 631:755–759（2024-07-24，DOI 10.1038/s41586-024-07566-y）',
    byline: 'Shumailov 等',
    note: '第九代退化为重复的 jackrabbit 列表；保留 10% 原始数据只减缓不阻止',
    tags: ['EP36', 'Nature', '模型崩塌'],
    episode: 36,
    date: '2026-10-18',
  },
  {
  // source: output/episodes/ep36-self-feeding/2026-10-18-breakdown.md
    kind: 'paper',
    title: 'Physical Review Letters（DOI 10.1103/156q-3ngc）',
    byline: '存档记为 King’s College London / 挪威科技大学 / 国际理论物理中心，官方新闻 2026-05-14；未记题名与作者名单',
    note: '加入一条外部数据即可阻止，且机器数据量无限大时仍有效；加入先验亦有类似效果。',
    tags: ['EP36', '期刊', '单条真数据'],
    episode: 36,
    date: '2026-10-18',
  },
  {
  // source: output/episodes/ep36-self-feeding/2026-10-18-breakdown.md
    kind: 'paper',
    title: 'ICML 2026 海报 #2707（存档未记题名）',
    byline: 'Qiao, Du, Liu, Zhang, Mai, Zhang, Pang',
    note: '低资源验证条件下，验证者只见目标分布的一小块、破碎、有偏的切片；筛选优先保留贴近本地流形的样本、剪掉全局相关的尾部。',
    tags: ['EP36', 'ICML 2026', '验证者'],
    episode: 36,
    date: '2026-10-18',
  },
  {
  // source: output/episodes/ep31-trust-the-done/2026-10-13-breakdown.md
    kind: 'paper',
    title: 'EvasionBench（arXiv 2609.30217）',
    byline: '存档只记编号与规模，未记作者',
    note: '50 个 task-policy 对；best-of-3 规避尝试率最高 98%、成功率最高 88%。',
    tags: ['EP31', 'arXiv', '规避'],
    episode: 31,
    date: '2026-10-13',
  },
  {
  // source: output/episodes/ep9-memory-ops/breakdown.md
    kind: 'paper',
    title: 'Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory（arXiv 2504.19413）',
    byline: '作者 Chhikara/Khant/Aryan/Singh/Yadav，2025',
    note: '思路来源是把 RAG 从「检索文档」下沉到「检索用户画像事实」，并借鉴了记忆分层（User/Session/Agent）。',
    tags: ['EP9', 'arXiv', '长期记忆'],
    episode: 9,
    date: '2026-09-15',
  },
  {
  // source: output/episodes/ep9-memory-ops/breakdown.md
    kind: 'paper',
    title: 'Zep: A Temporal Knowledge Graph Architecture（arXiv 2501.13956）',
    byline: '存档记为 getzep.com 作者，未逐个记名；被引在 README 第 67 行',
    note: '核心灵感是把数据库的「双时态（bi-temporal）」思想搬进知识图谱。',
    tags: ['EP9', 'arXiv', '双时态'],
    episode: 9,
    date: '2026-09-15',
  },
  {
  // source: output/episodes/ep12-workstyle-portable/2026-09-18-breakdown.md
    kind: 'paper',
    title: 'AgentDiet（arXiv 2509.23586）',
    byline: 'ep12 只从 caveman 源码注释读到出处，未记作者',
    note: '注释写明移植自论文 AgentDiet（arXiv 2509.23586 §2.3.1/§4.2.5）：2 步滞后、1 步上下文、双阈值 500、只改写不删除',
    tags: ['EP12', 'arXiv', '源码注释'],
    episode: 12,
    date: '2026-09-18',
  },
  {
  // source: output/episodes/ep16-real-world-benchmarks/breakdown.md
    kind: 'paper',
    title: 'SWE-bench: Can Language Models Resolve Real-World GitHub Issues?（ICLR 2024 Oral）',
    byline: 'Princeton Carlos E. Jimenez、John Yang 等（README 第 159 行）',
    note: '「软件工程即任务」：把 issue→patch→测试 这条真实工作流整条搬进 benchmark（README.md:44-45）。',
    tags: ['EP16', 'ICLR 2024', 'benchmark'],
    episode: 16,
    date: '2026-09-24',
  },
  {
  // source: output/episodes/ep16-real-world-benchmarks/breakdown.md
    kind: 'paper',
    title: 'SWE-bench Multimodal（ICLR 2025）',
    byline: 'SWE-bench 团队（README 第 30 行）',
    note: '两篇奠基论文：ICLR 2024 Oral《SWE-bench: Can Language Models Resolve Real-World GitHub Issues?》（README.md:31）与 ICLR 2025《SWE-bench Multimodal》（:30）。仓库即这两篇论文的官方代码与数据。',
    tags: ['EP16', 'ICLR 2025', 'benchmark'],
    episode: 16,
    date: '2026-09-24',
  },
  {
  // source: cache/swe-smith/README.md + output/episodes/ep16-real-world-benchmarks/breakdown.md
    kind: 'paper',
    title: 'SWE-smith: Scaling Data for Software Engineering Agents（arXiv 2504.21798，NeurIPS 2025 D&B Spotlight）',
    byline: '一作同时是 SWE-agent 的核心作者（README 第 84–95 行的 BibTeX）',
    note: '它把"造题"这件事从手工活变成了流水线，README 第 51 行写的是 52k task instances，第 67 行写 250+ Environments——比 SWE-bench 的两千多道高了一个数量级。',
    tags: ['EP16', 'NeurIPS 2025', '合成数据'],
    episode: 16,
    date: '2026-09-24',
  },
  {
  // source: cache/osworld/README.md + output/episodes/ep16-real-world-benchmarks/page.md
    kind: 'paper',
    title: 'OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks in Real Computer Environments（arXiv 2404.07972，NeurIPS 2024）',
    byline: 'xlang-ai（README 第 287–292 行的 arXiv BibTeX；setup.py 的 author 字段是同一批人）',
    note: 'OSWorld 的 infeasible 哨兵：函数体只有一个 pass，专门标记 26 条不可完成任务——必须主动喊 FAIL 才算对；反过来能完成的任务喊 FAIL 直接 0 分',
    tags: ['EP16', 'NeurIPS 2024', '真环境'],
    episode: 16,
    date: '2026-09-24',
  },
  {
  // source: cache/helm/CITATION.bib + output/episodes/ep17-regression-evals/page.md
    kind: 'paper',
    title: 'Holistic Evaluation of Language Models（TMLR 2023）',
    byline: 'Percy 等 45 人（cache/helm/CITATION.bib，注明 Featured / Expert Certification）',
    note: '第二级 把题写成标准化场景 · HELM：DEFAULT_TEST_SIZE = 1000（注释写明是为统计显著性；剩余变成训练样本），抽题种子 np.random.seed(0) 写死。',
    tags: ['EP17', 'TMLR 2023', '标准化'],
    episode: 17,
    date: '2026-09-25',
  },
  {
  // source: cache/hypothesis/paper.md + output/episodes/ep19-judgments-that-run/page.md
    kind: 'paper',
    title: 'Hypothesis: A new approach to property-based testing',
    byline: 'David R. MacIver（paper.md 作者栏）',
    note: '第二级 框住输入 · hypothesis（框住输入）：106 个 py 文件 / 46,399 行 + Rust 317 行，只有一种数据结构在流动——tuple[ChoiceNode, ...]。「更简单」被压成全序 sort_key = (长度, 逐位索引)（shrinker.py:73-94），于是 15 条 shrink pass 互不通信也能协同。',
    tags: ['EP19', 'JOSS 2019', '属性测试'],
    episode: 19,
    date: '2026-09-27',
  },
];

export const repos: KnowledgeSource[] = [
  {
  // source: output/podcast-01-whisper-cpp.md
    kind: 'repo',
    title: 'ggml-org/whisper.cpp',
    byline: 'ggml-org/whisper.cpp',
    note: 'whisper.cpp 做了一件「败家子」一样的事：把这些 32 位浮点数，压成 4 到 8 位的整数。',
    tags: ['EP1', '开源', 'ggml-org'],
    episode: 1,
    date: '2026-09-08',
  },
  {
  // source: output/episodes/ep2-ecc/breakdown.md
    kind: 'repo',
    title: 'affaan-m/ECC',
    byline: 'affaan-m/ECC',
    note: '它的名字 ECC = Everything Claude Code，本质是把「软件工程的最佳实践」沉淀成机器能读的 markdown 规范。',
    tags: ['EP2', '开源', 'affaan-m'],
    episode: 2,
    date: '2026-09-09',
  },
  {
  // source: output/episodes/ep3-hermes-agent/script.md
    kind: 'repo',
    title: 'NousResearch/hermes-agent',
    byline: 'NousResearch/hermes-agent',
    note: '你在做的事，跟 Hermes 想做的是同一件事：让一个 AI 不再是每次都从零开始，而是带着记忆、带着你调教出来的本事，跟你一起往前走。',
    tags: ['EP3', '开源', 'NousResearch'],
    episode: 3,
    date: '2026-09-10',
  },
  {
  // source: output/episodes/ep4-n8n/script.md
    kind: 'repo',
    title: 'n8n-io/n8n',
    byline: 'n8n-io/n8n',
    note: 'n8n 本身不重，是个 Node 应用，一条 Docker 命令起在 5678 端口，你那台 16G 的 M4 跑它毫无压力，吃资源的是后面接进去的那台大模型。',
    tags: ['EP4', '开源', 'n8n-io'],
    episode: 4,
    date: '2026-09-10',
  },
  {
  // source: output/episodes/ep5-claude-code/script.md
    kind: 'repo',
    title: 'anthropics/claude-code',
    byline: 'anthropics/claude-code',
    note: '头一个，你用 Claude Code 用了几个月，手里其实攒了一堆经验——「我这么问它就很顺」「我那样弄它就开始犯傻」。',
    tags: ['EP5', '开源', 'anthropics', 'EP7'],
    episode: 5,
    date: '2026-09-11',
  },
  {
  // source: output/episodes/ep6-autogpt/page.md
    kind: 'repo',
    title: 'Significant-Gravitas/AutoGPT',
    byline: 'Significant-Gravitas/AutoGPT',
    note: '一条线：blocks/_base.py:777 那一行 if，把「块自己申报敏感」乘上「用户开没开安全模式」，判定在基类，结果落成数据库里的 REVIEW 状态。',
    tags: ['EP6', '开源', 'Significant-Gravitas'],
    episode: 6,
    date: '2026-09-12',
  },
  {
  // source: output/2026-09-12-script.md
    kind: 'repo',
    title: 'openai/codex',
    byline: 'openai/codex',
    note: '你 ep5 带走的那条范式，今天在 Codex 身上完整地再验了一遍：智能只放在一个地方 —— 模型理解你那句人话，其它全部交给机械的确定性锁死。',
    tags: ['EP7', '开源', 'openai'],
    episode: 7,
    date: '2026-09-12',
  },
  {
  // source: output/episodes/ep8-memory-stack/page.md
    kind: 'repo',
    title: 'thedotmack/claude-mem',
    byline: 'thedotmack/claude-mem',
    note: '能带走的细节：claude-mem 的「一万字符预算 + 整条丢弃（不截断）」的上下文拟合顺序、出箱表 + 指数退避（5s→25s→125s，封顶 10min）的崩溃不丢、双层隐私剥离。',
    tags: ['EP8', '开源', 'thedotmack'],
    episode: 8,
    date: '2026-09-14',
  },
  {
  // source: output/episodes/ep8-memory-stack/breakdown.md
    kind: 'repo',
    title: 'MemPalace/mempalace',
    byline: 'MemPalace/mempalace',
    note: 'mempalace/embedding.py — embedding 工厂：minilm（all-MiniLM-L6-v2，384 维）/ embeddinggemma（MRL 截断到 384 维，批 32）/ openai-compat（服务端维度）。',
    tags: ['EP8', '开源', 'MemPalace'],
    episode: 8,
    date: '2026-09-14',
  },
  {
  // source: output/episodes/ep8-memory-stack/breakdown.md
    kind: 'repo',
    title: 'Graphify-Labs/graphify',
    byline: 'Graphify-Labs/graphify',
    note: '图默认存本地 graphify-out/graph.json（NetworkX node_link JSON），跨仓全局图在 ~/.graphify/global-graph.json + global-manifest.json，用 sha256[:16] 做文件指纹增量合并。',
    tags: ['EP8', '开源', 'Graphify-Labs'],
    episode: 8,
    date: '2026-09-14',
  },
  {
  // source: output/episodes/ep9-memory-ops/page.md
    kind: 'repo',
    title: 'mem0ai/mem0',
    byline: 'mem0ai/mem0',
    note: '能带走的细节：mem0 的「先提炼再存」+「三路融合检索（语义+BM25+实体）」+「md5 指纹去重 + 只增不删」+「0.95 认亲 / 0.5 提权」双阈值。',
    tags: ['EP9', '开源', 'mem0ai'],
    episode: 9,
    date: '2026-09-15',
  },
  {
  // source: output/episodes/ep9-memory-ops/breakdown.md
    kind: 'repo',
    title: 'getzep/graphiti',
    byline: 'getzep/graphiti',
    note: 'search（graphiti.py:1586）反向：query → 四路并行（bm25 + 余弦 + bfs）→ reranker → SearchFilters 时间过滤 → 返回。',
    tags: ['EP9', '开源', 'getzep'],
    episode: 9,
    date: '2026-09-15',
  },
  {
  // source: output/episodes/ep9-memory-ops/page.md
    kind: 'repo',
    title: 'basicmachines-co/basic-memory',
    byline: 'basicmachines-co/basic-memory',
    note: 'basic-memory 的「文件是唯一真相，数据库可重建」+「定宽字符串存时间 + 两次基准探测拒绝相对时间」+「删文件即忘，SET NULL 留断链」。',
    tags: ['EP9', '开源', 'basicmachines-co'],
    episode: 9,
    date: '2026-09-15',
  },
  {
  // source: output/episodes/ep10-skills-portable/page.md
    kind: 'repo',
    title: 'nexu-io/open-design',
    byline: 'nexu-io/open-design',
    note: '核心理念「提示栈就是产品」。拼装顺序 = 设计规范 → 通用工艺规则（craft，11 条）→ 技能正文，冲突时品牌赢 token 值、craft 兜底通用规则。',
    tags: ['EP10', '开源', 'nexu-io'],
    episode: 10,
    date: '2026-09-16',
  },
  {
  // source: output/episodes/ep10-skills-portable/page.md
    kind: 'repo',
    title: 'obra/superpowers',
    byline: 'obra/superpowers',
    note: '启动钩子把入口技能全文注入（matcher startup|clear|compact，同步执行），配 12 行「借口→现实」对照表。同一段注入要按平台输出三种 JSON 形状（Cursor 平铺 additional_context / Claude Code 嵌套 hookSpecificOutput / 其余 additionalContext）',
    tags: ['EP10', '开源', 'obra'],
    episode: 10,
    date: '2026-09-16',
  },
  {
  // source: output/episodes/ep10-skills-portable/breakdown.md
    kind: 'repo',
    title: 'anthropics/skills',
    byline: 'anthropics/skills',
    note: 'skills/skill-creator/SKILL.md（485 行）—— 造技能用的技能，整个仓库里最有信息量的一个文件。',
    tags: ['EP10', '开源', 'anthropics'],
    episode: 10,
    date: '2026-09-16',
  },
  {
  // source: output/episodes/ep11-knowledge-assets/breakdown.md
    kind: 'repo',
    title: 'microsoft/markitdown',
    byline: 'microsoft/markitdown',
    note: 'markitdown 的两个优先级常量：PRIORITY_SPECIFIC_FILE_FORMAT = 0.0、PRIORITY_GENERIC_FILE_FORMAT = 10.0（_markitdown.py:102-107）。',
    tags: ['EP11', '开源', 'microsoft'],
    episode: 11,
    date: '2026-09-17',
  },
  {
  // source: output/episodes/ep11-knowledge-assets/breakdown.md
    kind: 'repo',
    title: 'docling-project/docling',
    byline: 'docling-project/docling',
    note: 'DoclingDocument 的顶层字段里，body 和 furniture 都是 GroupItem 类型的根节点（docling_core/types/doc/document.py:186-191）。',
    tags: ['EP11', '开源', 'docling-project'],
    episode: 11,
    date: '2026-09-17',
  },
  {
  // source: output/episodes/ep11-knowledge-assets/page.md
    kind: 'repo',
    title: 'DietrichGebert/ponytail',
    byline: 'DietrichGebert/ponytail',
    note: 'ponytail 落在本周主题「攒得住的东西」内，但不在 09-17 那行给的日方向（「知识怎么变成资产」）上——它更贴 09-19 的「把判断写成清单 / 不变量」。',
    tags: ['EP11', '开源', 'DietrichGebert'],
    episode: 11,
    date: '2026-09-17',
  },
  {
  // source: output/episodes/ep12-workstyle-portable/2026-09-18-breakdown.md
    kind: 'repo',
    title: 'farion1231/cc-switch',
    byline: 'farion1231/cc-switch',
    note: 'CC Switch（farion1231/cc-switch）：Rust 写的桌面软件，把一台电脑上九个 AI 编程工具的供应商配置、密钥、MCP 服务、技能统一管起来，一键切换。',
    tags: ['EP12', '开源', 'farion1231'],
    episode: 12,
    date: '2026-09-18',
  },
  {
  // source: output/episodes/ep12-workstyle-portable/2026-09-18-breakdown.md
    kind: 'repo',
    title: 'JuliusBrussee/caveman',
    byline: 'JuliusBrussee/caveman',
    note: '【Caveman】 五步：① 请求出网前经本机代理（127.0.0.1:8787）→ ② 把上下文交给改写模型压一遍 → ③ 结果进 rewriter/gate.go 的确定性闸门 → ④ 通过则替换、不过则原样保留（原文定义「永远保持可翻转但未翻转」状态）→ ⑤ 用量落本地，可按试用周期导出报告。',
    tags: ['EP12', '开源', 'JuliusBrussee'],
    episode: 12,
    date: '2026-09-18',
  },
  {
  // source: output/episodes/ep12-workstyle-portable/2026-09-18-breakdown.md
    kind: 'repo',
    title: 'langchain-ai/langchain',
    byline: 'langchain-ai/langchain',
    note: 'libs/core/langchain_core/runnables/base.py（6,725 行）— 协议本体：invoke/ainvoke/batch/stream/astream 与四个可覆写钩子。',
    tags: ['EP12', '开源', 'langchain-ai'],
    episode: 12,
    date: '2026-09-18',
  },
  {
  // source: output/episodes/ep13-judgment-lists/2026-09-19-breakdown.md
    kind: 'repo',
    title: 'trufflesecurity/trufflehog',
    byline: 'trufflesecurity/trufflehog',
    note: '【trufflehog】 六步：① 数据源把内容切成块（chunk）送进引擎 → ② 每块过 5 个默认解码器（UTF8 必须排第一，去重逻辑依赖它。',
    tags: ['EP13', '开源', 'trufflesecurity'],
    episode: 13,
    date: '2026-09-19',
  },
  {
  // source: output/episodes/ep13-judgment-lists/page.md
    kind: 'repo',
    title: 'astral-sh/ruff',
    byline: 'astral-sh/ruff',
    note: '第二级 知道多确定 · ruff：codes.rs 1419 行、984 条手写配对、59 个来源。',
    tags: ['EP13', '开源', 'astral-sh'],
    episode: 13,
    date: '2026-09-19',
  },
  {
  // source: output/episodes/ep13-judgment-lists/page.md
    kind: 'repo',
    title: 'bufbuild/buf',
    byline: 'bufbuild/buf',
    note: '第三级 变成契约 · buf：规则定义 414 行、326 次登记、三套规格（105 / 110 / 111）、18 个分类。',
    tags: ['EP13', '开源', 'bufbuild'],
    episode: 13,
    date: '2026-09-19',
  },
  {
  // source: output/episodes/ep14-formats-that-last/breakdown.md
    kind: 'repo',
    title: 'safetensors/safetensors',
    byline: 'safetensors/safetensors',
    note: '关键文件与值：safetensors 的 safetensors/src/tensor.rs（常量 N_LEN = 8、MAX_HEADER_SIZE = 100_000_000、14 个错误变体、22 个 dtype）。',
    tags: ['EP14', '开源', 'safetensors'],
    episode: 14,
    date: '2026-09-20',
  },
  {
  // source: output/episodes/ep14-formats-that-last/page.md
    kind: 'repo',
    title: 'ggml-org/llama.cpp',
    byline: 'ggml-org/llama.cpp',
    note: '第二级 把「怎么读我」写进文件 · GGUF：magic 是四个字母 GGUF，版本号 u32 写死 3，接着是张量数与 KV 条数，然后一张元数据表（字符串键 + 4 字节类型 + 值，类型共 13 种，有编译期断言锁住这个数）、一张张量表（名字 / 维数 / 各维 / 类型 / 偏移），最后数据区按 32 字节对齐（general.alignment 可覆盖',
    tags: ['EP14', '开源', 'ggml-org'],
    episode: 14,
    date: '2026-09-20',
  },
  {
  // source: output/episodes/ep14-formats-that-last/page.md
    kind: 'repo',
    title: 'onnx/onnx',
    byline: 'onnx/onnx',
    note: '第三级 把承诺写成合同 · ONNX：两套互相独立的版本轴——IR 版本（结构，当前最大 14，最早那版直接叫 2017-10-10）与 opset（算子集，默认域 1–29，已发布 28），官方版本原则文档写明 IR 演进通常更慢。',
    tags: ['EP14', '开源', 'onnx'],
    episode: 14,
    date: '2026-09-20',
  },
  {
  // source: output/episodes/ep15-assertions/breakdown.md
    kind: 'repo',
    title: 'promptfoo/promptfoo',
    byline: 'promptfoo/promptfoo',
    note: 'promptfoo：66 种基础断言 + 3 种特殊（AssertionTypeSchema 由 BaseAssertionTypesSchema / NotPrefixed / Special / Redteam 四路 union）。',
    tags: ['EP15', '开源', 'promptfoo'],
    episode: 15,
    date: '2026-09-21',
  },
  {
  // source: output/episodes/ep15-assertions/breakdown.md
    kind: 'repo',
    title: 'guardrails-ai/guardrails',
    byline: 'guardrails-ai/guardrails',
    note: 'guardrails/guard.py:219-227 —— 疑问：重做次数默认几次？ 源码答案：_set_num_reasks 在 num_reasks 为 None 时落 1，并打一行 debug 说明「默认 1」。',
    tags: ['EP15', '开源', 'guardrails-ai'],
    episode: 15,
    date: '2026-09-21',
  },
  {
  // source: output/episodes/ep15-assertions/breakdown.md
    kind: 'repo',
    title: 'NVIDIA/garak',
    byline: 'NVIDIA/garak',
    note: 'garak/evaluators/base.py:53-60 / 492-501 —— 疑问：分数高是好还是坏？ 源码答案：坏。',
    tags: ['EP15', '开源', 'NVIDIA'],
    episode: 15,
    date: '2026-09-21',
  },
  {
  // source: output/episodes/ep16-real-world-benchmarks/breakdown.md
    kind: 'repo',
    title: 'SWE-bench/SWE-bench',
    byline: 'SWE-bench/SWE-bench',
    note: '300 / seed=42 —— SWE-bench Lite 抽样题数与随机种子，collect/make_lite/make_lite.py:68,81。',
    tags: ['EP16', '开源', 'SWE-bench'],
    episode: 16,
    date: '2026-09-24',
  },
  {
  // source: output/episodes/ep16-real-world-benchmarks/breakdown.md
    kind: 'repo',
    title: 'xlang-ai/OSWorld',
    byline: 'xlang-ai/OSWorld',
    note: '所以 OSWorld 提供 scripts/python/manual_examine.py 和 monitor/ 来人工复核（README :223-243）——这本身就是"机器判分不可全信"的自我承认。',
    tags: ['EP16', '开源', 'xlang-ai'],
    episode: 16,
    date: '2026-09-24',
  },
  {
  // source: output/episodes/ep16-real-world-benchmarks/breakdown.md
    kind: 'repo',
    title: 'SWE-bench/SWE-smith',
    byline: 'SWE-bench/SWE-smith',
    note: '同时，每道题会在 SWE-smith 组织的镜像仓库里推一条同名分支，分支上有两个提交：Bug Patch（注入 bug）+ Remove F2P Tests（删掉会暴露答案的测试文件）（gather.py:531-558）。',
    tags: ['EP16', '开源', 'SWE-bench'],
    episode: 16,
    date: '2026-09-24',
  },
  {
  // source: output/episodes/ep17-regression-evals/breakdown.md
    kind: 'repo',
    title: 'EleutherAI/lm-evaluation-harness',
    byline: 'EleutherAI/lm-evaluation-harness',
    note: 'lm-evaluation-harness 是一套「把同一份评测题目（YAML 声明的数据集 + Jinja 模板 + 指标），原样喂给任意后端模型，并输出可跨模型直接对比的分数与标准误」的评测协议层——它的核心资产不是那 13988 个任务 YAML',
    tags: ['EP17', '开源', 'EleutherAI'],
    episode: 17,
    date: '2026-09-25',
  },
  {
  // source: output/episodes/ep17-regression-evals/breakdown.md
    kind: 'repo',
    title: 'stanford-crfm/helm',
    byline: 'stanford-crfm/helm',
    note: 'HELM 固定种子：downsample_eval_instances 里 np.random.seed(0)（runner.py:123），few-shot 抽样也 random.seed(seed)、seed 就是 trial 序号（in_context_learning_adapter.py:148、runner.py:76）。',
    tags: ['EP17', '开源', 'stanford-crfm'],
    episode: 17,
    date: '2026-09-25',
  },
  {
  // source: output/episodes/ep17-regression-evals/breakdown.md
    kind: 'repo',
    title: 'UKGovernmentBEIS/inspect_ai',
    byline: 'UKGovernmentBEIS/inspect_ai',
    note: 'inspect_ai：DEFAULT_EPOCHS = 1，多次重复后用归约器合成（内置 9 个），pass_at_k 在轮次不够时返回 NaN 而不是假的 1.0。',
    tags: ['EP17', '开源', 'UKGovernmentBEIS'],
    episode: 17,
    date: '2026-09-25',
  },
  {
  // source: output/episodes/ep18-eval-landing/2026-09-26-breakdown.md
    kind: 'repo',
    title: 'confident-ai/deepeval',
    byline: 'confident-ai/deepeval',
    note: 'deepeval/plugins/plugin.py（128 行） — 「接进现成流水线」的接口：pytest_runtest_call 把每个测试包进 Observer（:85-107）。',
    tags: ['EP18', '开源', 'confident-ai'],
    episode: 18,
    date: '2026-09-26',
  },
  {
  // source: output/episodes/ep18-eval-landing/2026-09-26-breakdown.md
    kind: 'repo',
    title: 'mlflow/mlflow',
    byline: 'mlflow/mlflow',
    note: 'mlflow 是「接进平台」：它不重写指标，而是把外面六个评测库收编成自己的适配器——deepeval 30 个、ragas 30 个、trulens 10 个、guardrails 6 个、phoenix 5 个、google_adk 5 个，合计 86 个指标进一张注册表。',
    tags: ['EP18', '开源', 'mlflow'],
    episode: 18,
    date: '2026-09-26',
  },
  {
  // source: output/episodes/ep18-eval-landing/2026-09-26-breakdown.md
    kind: 'repo',
    title: 'langfuse/langfuse',
    byline: 'langfuse/langfuse',
    note: 'LANGFUSE_OTEL_MAX_SPAN_BYTES = 9_500_000：默认 9.5 MB，注释写「just under ClickHouse\'s 10MB min_chunk_bytes_for_parallel_parsing default」。',
    tags: ['EP18', '开源', 'langfuse'],
    episode: 18,
    date: '2026-09-26',
  },
  {
  // source: output/episodes/ep19-judgments-that-run/breakdown.md
    kind: 'repo',
    title: 'boxed/mutmut',
    byline: 'boxed/mutmut',
    note: '原函数定义保留但套上 @_mutmut_mutated(mutants_xxx)（:531-537），原实现改名为 xxx__mutmut_orig（:540），每个变异体改名 xxx__mutmut_{i+1}（:544），最后用一个模块级 MutantDict 把名字映射到函数对象。',
    tags: ['EP19', '开源', 'boxed'],
    episode: 19,
    date: '2026-09-27',
  },
  {
  // source: output/episodes/ep19-judgments-that-run/page.md
    kind: 'repo',
    title: 'HypothesisWorks/hypothesis',
    byline: 'HypothesisWorks/hypothesis',
    note: '第二级 框住输入 · hypothesis（框住输入）：106 个 py 文件 / 46,399 行 + Rust 317 行，只有一种数据结构在流动——tuple[ChoiceNode, ...]。',
    tags: ['EP19', '开源', 'HypothesisWorks'],
    episode: 19,
    date: '2026-09-27',
  },
  {
  // source: output/episodes/ep19-judgments-that-run/breakdown.md
    kind: 'repo',
    title: 'google/clusterfuzz',
    byline: 'google/clusterfuzz',
    note: 'ClusterFuzz 为此付出的全部代价是：帧数封顶 3、地址打码、数字打码、每行截断 80 字符，以及只有 5 类崩溃豁免这套归一化（data_types.py:43-52）。',
    tags: ['EP19', '开源', 'google'],
    episode: 19,
    date: '2026-09-27',
  },
  {
  // source: output/episodes/ep20-model-swap/breakdown.md
    kind: 'repo',
    title: 'andrewyng/aisuite',
    byline: 'andrewyng/aisuite',
    note: '台阶从薄到厚：aisuite（改一个字符串）→ litellm（差异收进映射表）→ pydantic-ai（换完之后输出还得对得上）。',
    tags: ['EP20', '开源', 'andrewyng'],
    episode: 20,
    date: '2026-09-28',
  },
  {
  // source: output/episodes/ep20-model-swap/breakdown.md
    kind: 'repo',
    title: 'BerriAI/litellm',
    byline: 'BerriAI/litellm',
    note: 'litellm/utils.py（约 13.7 万行量级，443KB） —— 客户端选择与包装，含 drop_params 的判定与 UnsupportedParamsError 的抛出点。',
    tags: ['EP20', '开源', 'BerriAI'],
    episode: 20,
    date: '2026-09-28',
  },
  {
  // source: output/episodes/ep20-model-swap/breakdown.md
    kind: 'repo',
    title: 'pydantic/pydantic-ai',
    byline: 'pydantic/pydantic-ai',
    note: 'pydantic-ai：DEFAULT_HTTP_TIMEOUT = 600，create_async_http_client(*, timeout=600, connect=5)。',
    tags: ['EP20', '开源', 'pydantic'],
    episode: 20,
    date: '2026-09-28',
  },
  {
  // source: output/episodes/ep21-template-updates/breakdown.md
    kind: 'repo',
    title: 'cookiecutter/cookiecutter',
    byline: 'cookiecutter/cookiecutter',
    note: 'cookiecutter 自己只加了两道：空包检查 len(namelist()) == 0（:71-73）、首个条目必须以 / 结尾（:77-80）。',
    tags: ['EP21', '开源', 'cookiecutter'],
    episode: 21,
    date: '2026-10-01',
  },
  {
  // source: output/episodes/ep21-template-updates/breakdown.md
    kind: 'repo',
    title: 'copier-org/copier',
    byline: 'copier-org/copier',
    note: '选它：只有模板根目录放了 {{ _copier_conf.answers_file }}.jinja 才被识别（_main.py:1148-1152），换来「同一项目叠多个模板」。',
    tags: ['EP21', '开源', 'copier-org'],
    episode: 21,
    date: '2026-10-01',
  },
  {
  // source: output/episodes/ep21-template-updates/breakdown.md
    kind: 'repo',
    title: 'nrwl/nx',
    byline: 'nrwl/nx',
    note: 'Nx Console（VS Code 插件）路径才 spawn 子进程：migrate-ui-api.ts:188-205 用位置参数传 10 个值，run-migration-process.js 跑完往 stdout 打一行 JSON 再 process.exit(0/1)。',
    tags: ['EP21', '开源', 'nrwl'],
    episode: 21,
    date: '2026-10-01',
  },
  {
  // source: output/episodes/ep22-executable-handover/page.md
    kind: 'repo',
    title: 'runmedev/runme',
    byline: 'runmedev/runme',
    note: 'runme（第一级，放在文档里）：Markdown 里那段命令本来就写着「第一步」，它让那一段真的能按下去。',
    tags: ['EP22', '开源', 'runmedev'],
    episode: 22,
    date: '2026-10-02',
  },
  {
  // source: output/episodes/ep22-executable-handover/breakdown.md
    kind: 'repo',
    title: 'casey/just',
    byline: 'casey/just',
    note: 'just 明确不做这件事，它的 README 里直言 make 那套复杂和怪脾气它绕开了大半，最典型的就是不需要写那句「声明这不是个文件」的伪目标标记。',
    tags: ['EP22', '开源', 'casey'],
    episode: 22,
    date: '2026-10-02',
  },
  {
  // source: output/episodes/ep22-executable-handover/page.md
    kind: 'repo',
    title: 'pre-commit/pre-commit',
    byline: 'pre-commit/pre-commit',
    note: 'ep20 问「换个模型还认不认」，ep21 问「换个项目，模板还能不能跟着长大」，ep22 把「换」的对象换成人：换一个人来接手，你攒下的东西还能不能照样跑对。',
    tags: ['EP22', '开源', 'pre-commit'],
    episode: 22,
    date: '2026-10-02',
  },
  {
  // source: output/episodes/ep23-vendor-swap/script.md
    kind: 'repo',
    title: 'open-telemetry/opentelemetry-python',
    byline: 'open-telemetry/opentelemetry-python',
    note: '本期三个项目：OpenTelemetry 的 Python SDK（当前版本 1.45.0，语义约定 0.66b0，2026 年 9 月 25 日发布）、OpenTelemetry Collector（当前版本 1.68.0 / 0.162.0，2026 年 9 月 28 日发布）、Jaeger（当前版本 2.21.0，2026 年 9 月 14 日发布）。',
    tags: ['EP23', '开源', 'open-telemetry'],
    episode: 23,
    date: '2026-10-03',
  },
  {
  // source: output/episodes/ep23-vendor-swap/breakdown.md
    kind: 'repo',
    title: 'open-telemetry/opentelemetry-collector',
    byline: 'open-telemetry/opentelemetry-collector',
    note: 'opentelemetry-sdk/src/opentelemetry/sdk/trace/__init__.py（1425 行）：SDK 核心，TracerProvider / Tracer / Span / SpanLimits。',
    tags: ['EP23', '开源', 'open-telemetry'],
    episode: 23,
    date: '2026-10-03',
  },
  {
  // source: output/episodes/ep23-vendor-swap/page.md
    kind: 'repo',
    title: 'jaegertracing/jaeger',
    byline: 'jaegertracing/jaeger',
    note: '后端自己也被协议吃掉了——Jaeger v2 注册 33 个组件工厂，其中 23 个是从 Collector 转发过来的壳，二十三个壳加起来 184 行。',
    tags: ['EP23', '开源', 'jaegertracing'],
    episode: 23,
    date: '2026-10-03',
  },
  {
  // source: output/episodes/ep24-machine-repro/breakdown.md
    kind: 'repo',
    title: 'astral-sh/uv',
    byline: 'astral-sh/uv',
    note: 'lock/mod.rs:98：const VERSION: u32 = 1; —— 整个锁文件格式只有一个主版本号。',
    tags: ['EP24', '开源', 'astral-sh'],
    episode: 24,
    date: '2026-10-04',
  },
  {
  // source: output/episodes/ep24-machine-repro/breakdown.md
    kind: 'repo',
    title: 'prefix-dev/pixi',
    byline: 'prefix-dev/pixi',
    note: '差异带来的代价也很直接——pixi 自己的 pixi.lock 有 11536 行、620 条包记录，人类已经不可能用眼睛审了。',
    tags: ['EP24', '开源', 'prefix-dev'],
    episode: 24,
    date: '2026-10-04',
  },
  {
  // source: output/episodes/ep24-machine-repro/breakdown.md
    kind: 'repo',
    title: 'jetify-com/devbox',
    byline: 'jetify-com/devbox',
    note: '具体到 devbox：写 /nix/store/vx7li94...-fd-10.5.0，而不是写「apt install fd」。',
    tags: ['EP24', '开源', 'jetify-com'],
    episode: 24,
    date: '2026-10-04',
  },
  {
  // source: output/episodes/ep25-dependency-rot/breakdown.md
    kind: 'repo',
    title: 'ossf/scorecard',
    byline: 'ossf/scorecard',
    note: '环境变量：SCORECARD_EXPERIMENTAL（checks/all_checks.go:38，存在才带上两个实验检查）、GH_HOST（clients/githubrepo/client.go:165-170、367-383，非 github.com 走 Enterprise URL）。',
    tags: ['EP25', '开源', 'ossf'],
    episode: 25,
    date: '2026-10-06',
  },
  {
  // source: output/episodes/ep25-dependency-rot/breakdown.md
    kind: 'repo',
    title: 'dependabot/dependabot-core',
    byline: 'dependabot/dependabot-core',
    note: '而且 DependabotError#sanitize_message（:457-466）在构造时就自动抹掉 basic-auth 凭据和临时目录路径——凭据脱敏做在异常类的构造函数里，不是做在日志出口。',
    tags: ['EP25', '开源', 'dependabot'],
    episode: 25,
    date: '2026-10-06',
  },
  {
  // source: output/episodes/ep25-dependency-rot/breakdown.md
    kind: 'repo',
    title: 'renovatebot/renovate',
    byline: 'renovatebot/renovate',
    note: 'Renovate：cron 与自然语言并存，且强制 cron 的分钟位必须是 *（schedule.ts:44-57，不符合就整条 schedule 判为非法，然后降级为「总是可以」而不是报错拒绝，:152-156）。',
    tags: ['EP25', '开源', 'renovatebot'],
    episode: 25,
    date: '2026-10-06',
  },
  {
  // source: output/episodes/ep26-silent-defaults/breakdown.md
    kind: 'repo',
    title: 'python/mypy',
    byline: 'python/mypy',
    note: 'mypy：unused-ignore 这条错误码在源码里就是 default_enabled=False。',
    tags: ['EP26', '开源', 'python'],
    episode: 26,
    date: '2026-10-07',
  },
  {
  // source: output/episodes/ep26-silent-defaults/breakdown.md
    kind: 'repo',
    title: 'pytest-dev/pytest',
    byline: 'pytest-dev/pytest',
    note: '配置项的默认 False，它下面挂着 strict_config、strict_markers、strict_xfail。',
    tags: ['EP26', '开源', 'pytest-dev'],
    episode: 26,
    date: '2026-10-07',
  },
  {
  // source: output/episodes/ep26-silent-defaults/breakdown.md
    kind: 'repo',
    title: 'sqlalchemy/alembic',
    byline: 'sqlalchemy/alembic',
    note: 'alembic：compare_server_default 默认 False；compare_type 是 1.12.0 才从 False',
    tags: ['EP26', '开源', 'sqlalchemy'],
    episode: 26,
    date: '2026-10-07',
  },
  {
  // source: output/episodes/ep27-rule-rot/2026-10-08-breakdown.md
    kind: 'repo',
    title: 'open-policy-agent/opa',
    byline: 'open-policy-agent/opa',
    note: 'v1.0 把 in / every / if / contains 四个关键字变成默认；future.keywords 系列导入变成空操作。',
    tags: ['EP27', '开源', 'open-policy-agent'],
    episode: 27,
    date: '2026-10-08',
  },
  {
  // source: output/episodes/ep27-rule-rot/2026-10-08-breakdown.md
    kind: 'repo',
    title: 'open-policy-agent/conftest',
    byline: 'open-policy-agent/conftest',
    note: '全文件 19 行，唯一逻辑就是退出码传递，注释里写明理由是 issue #741「让脚本和 CI 能依赖它」。',
    tags: ['EP27', '开源', 'open-policy-agent'],
    episode: 27,
    date: '2026-10-08',
  },
  {
  // source: output/episodes/ep28-verified-expiry/2026-10-09-breakdown.md
    kind: 'repo',
    title: 'sigstore/cosign',
    byline: 'sigstore/cosign',
    note: '第 32–33 行即口播里"两行"的出处：有效期 = 10 分钟，写死在发证函数里。',
    tags: ['EP28', '开源', 'sigstore'],
    episode: 28,
    date: '2026-10-09',
  },
  {
  // source: output/episodes/ep28-verified-expiry/2026-10-09-breakdown.md
    kind: 'repo',
    title: 'sigstore/sigstore-python',
    byline: 'sigstore/sigstore-python',
    note: '它对本期判断不增加新东西，进口播只是名字负担',
    tags: ['EP28', '开源', 'sigstore'],
    episode: 28,
    date: '2026-10-09',
  },
  {
  // source: output/episodes/ep29-backup-rot/2026-10-10-breakdown.md
    kind: 'repo',
    title: 'restic/restic',
    byline: 'restic/restic',
    note: '原文：默认的 check 做的是 *Structural consistency and integrity, e.g. snapshots, trees and pack files (default)*；要验实际备份的数据，是 *enabled with flags*。',
    tags: ['EP29', '开源', 'restic'],
    episode: 29,
    date: '2026-10-10',
  },
  {
  // source: output/episodes/ep29-backup-rot/2026-10-10-breakdown.md
    kind: 'repo',
    title: 'kopia/kopia',
    byline: 'kopia/kopia',
    note: '原文：kopia snapshot verify 在每次日常全量维护里自动跑；但它 *stops short of downloading, decrypting, and decompressing the blobs*',
    tags: ['EP29', '开源', 'kopia'],
    episode: 29,
    date: '2026-10-10',
  },
  {
  // source: output/episodes/ep29-backup-rot/2026-10-10-breakdown.md
    kind: 'repo',
    title: 'borgbackup/borg',
    byline: 'borgbackup/borg',
    note: 'verify_data=False 是 check() 的参数；verify_data() 内 logger.info("Starting cryptographic data integrity verification...")。',
    tags: ['EP29', '开源', 'borgbackup'],
    episode: 29,
    date: '2026-10-10',
  },
];

/** 最近六期：本仓只有 20 期带「一句话」，这里取其中最近 6 期（EP34–EP39）。 */
export const featuredEpisodes: EpisodeCard[] = [
  {
  // source: web/library/data/episodes.json · no=34 · date=2026-10-16 · chars=14841
    no: 34,
    title: '一件事交给 AI，人还需要判断什么',
    oneLiner: '判断力不是保证你对，是让你每一次都比同类人好一点点，然后把这一点点攒起来。',
    date: '2026-10-16',
    chars: 14841,
    minutes: 85,
    series: 'AI 交了这么多',
    url: '#episodes',
  },
  {
  // source: web/library/data/episodes.json · no=35 · date=2026-10-17 · chars=14610
    no: 35,
    title: '这周的 AI 变化，哪一件值得我认真理解',
    oneLiner: '交出来的东西变多十倍，先坏的通常不是模型那一层，是收的那一层。',
    date: '2026-10-17',
    chars: 14610,
    minutes: 83,
    series: 'AI 交了这么多',
    url: '#episodes',
  },
  {
  // source: web/library/data/episodes.json · no=36 · date=2026-10-18 · chars=14476
    no: 36,
    title: '自己喂自己，为什么越喂越窄',
    oneLiner: '「要有人在系统外面看一眼」这句话只检查了位置，没检查视野。',
    date: '2026-10-18',
    chars: 14476,
    minutes: 83,
    series: 'AI 交了这么多',
    url: '#episodes',
  },
  {
  // source: web/library/data/episodes.json · no=37 · date=2026-10-19 · chars=14394
    no: 37,
    title: '改一处就够，前提是你知道有几处',
    oneLiner: '只在一个地方维护，能保证你不自相矛盾；它不保证你不自欺。',
    date: '2026-10-19',
    chars: 14394,
    minutes: 82,
    series: '你攒下的东西',
    url: '#episodes',
  },
  {
  // source: web/library/data/episodes.json · no=38 · date=2026-10-21 · chars=14620
    no: 38,
    title: '没有报错，不等于做对了',
    oneLiner: '没有报错，可能只是因为它从来不打算报错。',
    date: '2026-10-21',
    chars: 14620,
    minutes: 84,
    series: '你攒下的东西',
    url: '#episodes',
  },
  {
  // source: web/library/data/episodes.json · no=39 · date=2026-10-22 · chars=14612
    no: 39,
    title: '交接的是决定，不是结果',
    oneLiner: '结果会被人改掉，决定才会被人守住。',
    date: '2026-10-22',
    chars: 14612,
    minutes: 83,
    series: '你攒下的东西',
    url: '#episodes',
  },
];

/**
 * 全库统计：直接取 episodes.json 头部的 count / judgment_count / repo_count /
 * chars_total / audio_minutes / first_date..last_date；audioHours = audio_minutes ÷ 60。
 * 语速口径与 config/agent.json 的 gates.length.chars_per_minute = 175 一致
 * （minutes = Math.round(chars / CHARS_PER_MINUTE)）。
 */
export const stats: {
  episodes: number;
  judgments: number;
  repos: number;
  chars: number;
  audioHours: number;
  span: string;
} = {
  // source: web/library/data/episodes.json → count / judgment_count / repo_count / chars_total / audio_minutes / first_date..last_date
  episodes: 39,
  judgments: 50,
  repos: 71,
  chars: 492368,
  audioHours: 8.1,
  span: '2026-09-08 — 2026-10-22',
};

/** 语速口径：config/agent.json → gates.length.chars_per_minute = 175（2026-10-03 用户拍板）。 */
export const CHARS_PER_MINUTE = 175;

/** 2 段真实试听：同一段文字的两把声音，均由 AI 合成（auditions.js 的 aiGenerated = true）。 */
export const audition: { name: string; subtitle: string; seconds: number; direction: string }[] = [
  {
  // source: web/library/data/auditions.js
    name: '松弛男声',
    subtitle: '像朋友陪你读书',
    seconds: 40.64,
    direction: '成年中文男声，中低音区，音色干净温暖，松弛自然，亲近但不耳语。像坐在窗边面对一位朋友聊天，清楚地说普通话。语速从容但不拖沓，句间有自然呼吸。不要广播腔，不要夸张煽情，不加背景音乐。',
  },
  {
  // source: web/library/data/auditions.js
    name: '清透女声',
    subtitle: '清楚，也有一点好奇',
    seconds: 36.8,
    direction: '成年中文女声，音色清透、柔和，有温度，声音有自然的空气感但不气声。像一位思路清晰的朋友陪你聊一本书，说普通话，语速适中。问句有一点自然的好奇，陈述句平实。不要广告腔，不要戏剧化，不加背景音乐。',
  },
];

/**
 * 介绍页「按需求找期」：把 episodes.json 的 9 条主题线翻成访客会问自己的那句话。
 *
 * 每条只放四样能核对的东西：问题（本页写的文案）、主题线、这条线一共几期、
 * 点开就是哪一期（期号 / 标题 / 日期全部照 episodes.json 抄，不手写）。
 * 「能帮你什么」是产品文案，不声称是原稿原话；判断本身在下面的 sampleEpisode 里逐字给出。
 *
 * 核对：node frontend/content.test.mjs 第 13 组会拿回 episodes.json 逐条比对。
 */
export interface NeedCard {
  /** 访客会问自己的那句话。 */
  question: string;
  /** episodes.json 里的主题线名，必须与数据一致。 */
  series: string;
  /** 页面上给访客看的名字；主题线名里带开发者说法时换成人话，缺省就用 series。 */
  label?: string;
  /** 这条线一共有几期。 */
  count: number;
  /** 点开就是这一期。 */
  pick: { no: number; title: string; date: string };
  /** 这一期能帮你什么（介绍页文案）。 */
  help: string;
}

export const needs: NeedCard[] = [
  {
  // source: web/library/data/episodes.json · series=算力取舍 · count=1 · pick: no=1 date=2026-09-08
    question: '这件事，值不值得我花时间？',
    series: '算力取舍',
    count: 1,
    pick: { no: 1, title: 'whisper.cpp', date: '2026-09-08' },
    help: '时间和机器都有限的时候，什么能省、什么不能省。这一期拆的是把一个语音模型放进自己电脑里跑。',
  },
  {
  // source: web/library/data/episodes.json · series=开源协作 · count=1 · pick: no=2 date=2026-09-09
    question: '一个人做不完的事，怎么让别人接得上？',
    series: '开源协作',
    count: 1,
    pick: { no: 2, title: 'ECC', date: '2026-09-09' },
    help: '二十五万人给一堆说明文件点星，靠的不是代码有多难，是别人照着它就能接上手。',
  },
  {
  // source: web/library/data/episodes.json · series=Agent 这层壳 · count=5 · pick: no=5 date=2026-09-11
    question: 'AI 帮我干活，它能替我做到哪一步？',
    series: 'Agent 这层壳',
    label: 'AI 助手能做什么',
    count: 5,
    pick: { no: 5, title: 'Agent（标本：Claude Code）', date: '2026-09-11' },
    help: '同一个模型，装进不同的壳里，能做的事差得很远。这一期比的是几个工具各自的边界和代价。',
  },
  {
  // source: web/library/data/episodes.json · series=攒得住的东西 · count=7 · pick: no=8 date=2026-09-14
    question: '手里的东西，怎么才攒得住？',
    series: '攒得住的东西',
    count: 7,
    pick: { no: 8, title: '攒得住的东西（记忆三件套：claude-mem / mempalace / graphify）', date: '2026-09-14' },
    help: '会话关掉、工具换掉以后，你手上还剩什么。这一期拆的是三个把记忆落到文件上的做法。',
  },
  {
  // source: web/library/data/episodes.json · series=攒下的东西，怎么验 · count=5 · pick: no=19 date=2026-09-27
    question: '我怎么知道，攒下的东西还靠得住？',
    series: '攒下的东西，怎么验',
    count: 5,
    pick: { no: 19, title: '攒下的东西，怎么验（七）', date: '2026-09-27' },
    help: '对错这件事，能交给一件不看过程的东西吗。这一期收在一句话上：判据得自己能跑起来。',
  },
  {
  // source: web/library/data/episodes.json · series=能不能带走 · count=5 · pick: no=20 date=2026-09-28
    question: '我换工具、换模型，东西还带得走吗？',
    series: '能不能带走',
    count: 5,
    pick: { no: 20, title: '攒下的东西，能不能带走（二）', date: '2026-09-28' },
    help: '「换模型只要改一个字符串」这句话，难的从来不是那个字符串。这一期把真正要动的地方列了出来。',
  },
  {
  // source: web/library/data/episodes.json · series=会不会自己烂掉 · count=6 · pick: no=27 date=2026-10-08
    question: '我不管它的时候，它会不会自己坏？',
    series: '会不会自己烂掉',
    count: 6,
    pick: { no: 27, title: '攒下的东西，会不会自己烂掉（三）', date: '2026-10-08' },
    help: '规则不会自己变旧，也不会通知你。这一期给了三句能问自己、也能拿去问别人的检查。',
  },
  {
  // source: web/library/data/episodes.json · series=AI 交了这么多 · count=6 · pick: no=34 date=2026-10-16
    question: 'AI 交出来的东西，我该信什么？',
    series: 'AI 交了这么多',
    count: 6,
    pick: { no: 34, title: '一件事交给 AI，人还需要判断什么', date: '2026-10-16' },
    help: '能写成规则的那部分会一直被拿走。这一期讲的是剩下那部分——人在一件事里的位置。',
  },
  {
  // source: web/library/data/episodes.json · series=你攒下的东西 · count=3 · pick: no=39 date=2026-10-22
    question: '我攒下的东西，怎么交接给别人？',
    series: '你攒下的东西',
    count: 3,
    pick: { no: 39, title: '交接的是决定，不是结果', date: '2026-10-22' },
    help: '结果会被人改掉，决定才会被人守住。这一期讲一份决策记录最少要有哪几样。',
  },
];

/**
 * 介绍页「每期给你什么」用的样本期：三条判断 + 一句话 + 出处，全部逐字照抄，
 * 一个字都不改写。选 ep27 是因为它正好三条判断、两个仓库、有「本期一句话」。
 *
 * 核对：content.test.mjs 第 13 组拿回 data.js 的 window.LIB 逐字比对。
 */
export interface EpisodeSample {
  no: number;
  title: string;
  date: string;
  series: string;
  /** data.js 里的 one_liner，一字不改。 */
  oneLiner: string;
  /** data.js 里的 judgments，一字不改，顺序不动。 */
  judgments: string[];
  /** data.js 里的 repos，一字不改。 */
  repos: string[];
}

export const sampleEpisode: EpisodeSample = {
  // source: web/library/data.js → window.LIB.episodes[no=27]（slug ep27-rule-rot）· date=2026-10-08
  no: 27,
  title: '攒下的东西，会不会自己烂掉（三）',
  date: '2026-10-08',
  series: '会不会自己烂掉',
  oneLiner: '规则不会自己变旧，也不会通知你。',
  judgments: [
    '改一处够不够——它是不是唯一出处？',
    '它有没有一条能跑的动作（不是写在文件里）？',
    '它失效的时候会不会有东西变？报错、拒绝、指纹变了都算。',
  ],
  repos: ['open-policy-agent/opa', 'open-policy-agent/conftest'],
};
