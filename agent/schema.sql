-- 播客 Agent 外环：状态表
-- 依据 docs/播客Agent架构设计.md §7.1。幂等，可重复执行（每次都 create if not exists）。
--
-- 三条设计约束（别在下游代码里破）：
--   1. 库是 info_source.db —— workbench_server.py 已经在读它，期次状态要能直接上页面，
--      所以刻意不另起一个 agent.db（两套库 = 又要对账）。
--   2. 文件仍是**产物**的真相源（稿子 / 笔记 / 音频），这里只存指针 + 指标 + 状态，
--      不做第二份内容副本。
--   3. episode_events 只追加。任何状态变化都留一条带时间戳的事件，出问题能回放
--      「那晚到底发生了什么」。不许 update、不许 delete。

-- 并发：外环写、workbench_server / 页面读。WAL 让读不阻塞写。
-- 注意 journal_mode 是写进库头的持久设置，改一次就生效，不是每连接一次性的。
PRAGMA journal_mode = WAL;

-- 期次状态：一期一行，唯一真相源。替代现在「靠文件 mtime 猜状态」的多个地方。
CREATE TABLE IF NOT EXISTS episodes (
  ep_no            INTEGER PRIMARY KEY,
  date             TEXT NOT NULL UNIQUE,
  -- 设计稿表里写的 stage 是 prepare|draft|verify|handoff|await_synth|fallback|publish|done，
  -- 实现按 agent/pipeline.py 的 STAGES 跑（多了 review，且带 _failed 后缀终态）。
  stage            TEXT NOT NULL,
  -- running|ok|short|failed|no_audio
  status           TEXT NOT NULL,
  repos            TEXT,              -- JSON 数组，一期多仓写多个
  script_path      TEXT,
  breakdown_path   TEXT,
  audio_path       TEXT,
  chars            INTEGER,           -- 正文汉字数（闸门口径）
  value_lines      INTEGER,           -- 含具体数字的行数（拆解笔记里）
  est_minutes      REAL,              -- 按 chars / chars_per_minute 推算
  actual_minutes   REAL,              -- ffprobe 实测
  attempt          INTEGER DEFAULT 0, -- 写稿已尝试轮数（含审稿回炉那轮）
  synth_route      TEXT,              -- doubao_app | local_voxcpm2
  model            TEXT,
  fail_reason      TEXT,
  -- 下面两列不在设计稿 §7.1 的表里，是实现时补的，理由写在这：
  --   review_round  —— max_review_rounds 的计数必须落在库里，否则外环重启后
  --                    会「忘了已经审过一轮」，把额度烧穿（见 §4.1 四条硬约束）。
  --   files_read    —— 内环回执里报的读文件数；C 层的上下文预算靠它留痕，
  --                    低于 config 的 min_files_read 判「读得太浅」（§4.3）。
  review_round     INTEGER DEFAULT 0,
  files_read       INTEGER,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);

-- 事件表：只追加。
CREATE TABLE IF NOT EXISTS episode_events (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  date   TEXT NOT NULL,
  ts     TEXT NOT NULL,
  stage  TEXT,
  -- stage_start|stage_ok|stage_fail|degraded|human_review|note|gate_drift|tool_call
  event  TEXT NOT NULL,
  detail TEXT
);

-- 每次外环启动一行：算耗时的，也是「一期到底烧了多少 token」的唯一记录点。
-- 积分口径查不到公开换算（设计稿 §12.1 第 1 条），所以这里只记不拦——先攒几期实测值。
CREATE TABLE IF NOT EXISTS agent_runs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  date        TEXT NOT NULL,
  started_at  TEXT NOT NULL,
  ended_at    TEXT,
  exit_stage  TEXT,
  exit_reason TEXT,
  model_calls INTEGER DEFAULT 0,
  est_tokens  INTEGER DEFAULT 0
);

-- 索引：status / report 两个查询都按日期倒序取最近几期。
CREATE INDEX IF NOT EXISTS idx_episodes_date      ON episodes(date DESC);
CREATE INDEX IF NOT EXISTS idx_events_date        ON episode_events(date, id DESC);
CREATE INDEX IF NOT EXISTS idx_runs_date          ON agent_runs(date DESC);
