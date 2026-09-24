# 第 16 期 · 攒下的东西，怎么验（四）——基准：拿真实世界当考卷（SWE-bench / OSWorld / SWE-smith）

- 上线：2026-09-24 夜班落稿
- 主题线：接 ep15「断言：不看过程怎么判对错」（promptfoo / guardrails / garak）；**本期转轴**：从「判据写在配置里」推到「考卷本身是真的还是人造的」——三级台阶＝真题 → 真环境 → 自己造题
- 标的：SWE-bench（`cache/swe-bench`，⭐5,897，包版本 5.0.2）× OSWorld（`cache/osworld`，⭐3,155，setup.py 1.0.1）× SWE-smith（`cache/swe-smith`，⭐784，0.0.9）｜ 主线：Agent/LLM 评测与基准
- repo: SWE-bench/SWE-bench
- repo: xlang-ai/OSWorld
- repo: SWE-bench/SWE-smith
- **信息截止：2026-09-24** ｜ 证据等级：SWE-bench / OSWorld 走 codeload tarball（6.0 MB / 22 MB），SWE-smith tarball 被截断、git clone 被 SSL 断，改走「Git Trees API 拿全树 + raw 逐文件抓」（171 个文件，1.9 MB）；星数 / 建仓 / 最近 push 当日现查 GitHub API
- 稿子：`output/2026-09-24-script.md`（= `output/latest-script.md`，主稿 13,120 汉字 + 本周新闻 2,024 汉字，合计 15,109）
- 拆解笔记：`output/2026-09-24-breakdown.md`（36 字段标题 = 整期人话导览 + 三项目各 12 字段 + 三项目各自的二次深读 / 取证台账 / 取舍台账 + 跨项目三级台阶对照表）
- 音频：待豆包那班（02:00）合成
- 本期三个最硬的句柄：
  1. SWE-bench 判分里的 `SUITE_RAN` 八行正则：区分「跑完没失败」与「压根没跑」，注释直接点出某个前端框架在浏览器挂掉时仍打印「Executed 0 of 0」，而 fail-only 模式下空结果=全通过
  2. OSWorld 的 `infeasible` 哨兵：函数体只有一个 `pass`，专门标记 26 条不可完成任务——必须主动喊 FAIL 才算对；反过来能完成的任务喊 FAIL 直接 0 分
  3. SWE-smith 推分支前 `os.remove` 掉 F2P 测试文件再提交「Remove F2P Tests」，配合 `rm -rf .git; git init` 做答案隔离

## 相关

- [[ep15-assertions]]：上一期，断言写在配置层（promptfoo / guardrails / garak），本期把它推到考卷层
- [[ep13-judgment-lists]]：把判断写成清单，本期的 FAIL_TO_PASS / PASS_TO_PASS 是同一条线的极端形态
- [[agent-map]]：现役评测与基准项目的常驻地图
